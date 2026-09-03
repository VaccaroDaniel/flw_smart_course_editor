<?php
// S5 verification helper: create/snapshot a teacher-authored Moodle Page in a Unit Section.

define('CLI_SCRIPT', true);

function cli_value(array $argv, string $name, ?string $default = null): ?string {
    $prefix = '--' . $name . '=';
    foreach ($argv as $index => $arg) {
        if (strpos($arg, $prefix) === 0) {
            return substr($arg, strlen($prefix));
        }
        if ($arg === '--' . $name && isset($argv[$index + 1])) {
            return $argv[$index + 1];
        }
    }
    return $default;
}

function json_out($value): string {
    return json_encode($value, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
}

$defaultconfigpath = getenv('FLW_MOODLE_CONFIG') ?: 'D:/Dev/MoodleWindowsInstaller-latest-501/server/moodle/public/config.php';
$configpath = cli_value($argv, 'config', $defaultconfigpath);
if (!file_exists($configpath)) {
    fwrite(STDERR, "Moodle config.php was not found at {$configpath}\n");
    exit(1);
}

require($configpath);
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/course/modlib.php');
require_once($CFG->dirroot . '/mod/page/lib.php');

global $argv, $DB, $USER, $PAGE, $CFG;

$action = cli_value($argv, 'action', 'snapshot');
$courseid = (int)cli_value($argv, 'courseid', '200');
$sectionid = (int)cli_value($argv, 'sectionid', '2175');
$cmidnumber = cli_value($argv, 'cmidnumber', 'S5_TEACHER_PAGE_REW_U023');
$reportpath = cli_value($argv, 'report', '');
$moodleurl = trim((string)cli_value($argv, 'moodle-url', ''));
if ($moodleurl !== '') {
    $CFG->wwwroot = rtrim($moodleurl, '/');
}

$actor = get_admin();
\core\session\manager::set_user($actor);
$USER = $actor;

$course = $DB->get_record('course', ['id' => $courseid], '*', MUST_EXIST);
$section = $DB->get_record('course_sections', ['id' => $sectionid, 'course' => $courseid], '*', MUST_EXIST);
$PAGE->set_context(context_course::instance($courseid));
$PAGE->set_course($course);

function section_activity_snapshot(stdClass $section): array {
    global $DB, $CFG;

    $sequence = trim((string)($section->sequence ?? ''));
    $cmids = $sequence === '' ? [] : array_values(array_filter(array_map('intval', explode(',', $sequence)), fn($id) => $id > 0));
    if (!$cmids) {
        return [];
    }
    [$insql, $params] = $DB->get_in_or_equal($cmids, SQL_PARAMS_NAMED, 'cmid');
    $records = $DB->get_records_sql(
        "SELECT cm.id, cm.course, cm.section, cm.instance, cm.idnumber, cm.visible, m.name AS module
           FROM {course_modules} cm
           JOIN {modules} m ON m.id = cm.module
          WHERE cm.id {$insql}
       ORDER BY cm.id ASC",
        $params
    );
    $rows = [];
    foreach ($records as $record) {
        $name = '';
        if ($record->module === 'page') {
            $name = (string)$DB->get_field('page', 'name', ['id' => (int)$record->instance]);
        } else if ($record->module === 'scorm') {
            $name = (string)$DB->get_field('scorm', 'name', ['id' => (int)$record->instance]);
        }
        $rows[] = [
            'cmid' => (int)$record->id,
            'module' => (string)$record->module,
            'instance' => (int)$record->instance,
            'idnumber' => (string)($record->idnumber ?? ''),
            'name' => $name,
            'visible' => (int)$record->visible,
            'url' => rtrim((string)$CFG->wwwroot, '/') . '/mod/' . $record->module . '/view.php?id=' . (int)$record->id,
        ];
    }
    return $rows;
}

if ($action === 'create') {
    $module = $DB->get_record('modules', ['name' => 'page'], 'id,name', MUST_EXIST);
    $existing = $DB->get_record('course_modules', [
        'course' => $courseid,
        'module' => (int)$module->id,
        'idnumber' => $cmidnumber,
    ], '*', IGNORE_MISSING);
    if (!$existing) {
        [, , , , $data] = prepare_new_moduleinfo_data($course, 'page', (int)$section->section);
        $data->name = 'S5 Teacher Page Preserve Fixture';
        $data->cmidnumber = $cmidnumber;
        $data->introeditor = [
            'text' => '<p>Teacher-authored page fixture for S5 preservation testing.</p>',
            'format' => FORMAT_HTML,
            'itemid' => file_get_unused_draft_itemid(),
        ];
        $data->content = '<p>This Page must remain in the Unit section when the FLW Unit SCORM is updated or superseded.</p>';
        $data->contentformat = FORMAT_HTML;
        $data->display = 5;
        $data->displayoptions = [];
        add_moduleinfo($data, $course);
        rebuild_course_cache($courseid, true);
    }
}

$section = $DB->get_record('course_sections', ['id' => $sectionid, 'course' => $courseid], '*', MUST_EXIST);
$activities = section_activity_snapshot($section);
$teacher = array_values(array_filter($activities, fn($row) => ($row['idnumber'] ?? '') === $cmidnumber));

$report = [
    'status' => $teacher ? 'PASS' : 'FAIL',
    'action' => $action,
    'timestamp' => date('c'),
    'courseId' => $courseid,
    'sectionId' => $sectionid,
    'sectionNumber' => (int)$section->section,
    'teacherPageIdnumber' => $cmidnumber,
    'teacherPage' => $teacher[0] ?? null,
    'activities' => $activities,
];
if ($reportpath !== '') {
    file_put_contents($reportpath, json_out($report));
}
echo json_out($report) . PHP_EOL;
exit($report['status'] === 'PASS' ? 0 : 2);
