<?php
// S8 verification helper for disposable safe-rebuild fixtures.

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

$configpath = cli_value($argv, 'config', getenv('FLW_MOODLE_CONFIG') ?: 'D:/Dev/MoodleWindowsInstaller-latest-501/server/moodle/config.php');
if (!file_exists($configpath)) {
    fwrite(STDERR, "Moodle config.php was not found at {$configpath}\n");
    exit(1);
}

require($configpath);
require_once($CFG->libdir . '/moodlelib.php');
require_once($CFG->libdir . '/enrollib.php');
require_once($CFG->libdir . '/gradelib.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/course/modlib.php');
require_once($CFG->libdir . '/completionlib.php');
require_once($CFG->dirroot . '/mod/page/lib.php');
require_once($CFG->dirroot . '/mod/scorm/lib.php');
require_once($CFG->dirroot . '/mod/scorm/locallib.php');

global $argv, $DB, $USER, $PAGE, $CFG;

$action = cli_value($argv, 'action', 'snapshot');
$courseid = (int)cli_value($argv, 'courseid', '0');
$sectionid = (int)cli_value($argv, 'sectionid', '0');
$cmidnumber = trim((string)cli_value($argv, 'cmidnumber', ''));
$packagepath = trim((string)cli_value($argv, 'package', ''));
$username = strtolower(trim((string)cli_value($argv, 'username', 's8_rebuild_probe_learner')));
$manualidnumber = trim((string)cli_value($argv, 'manual-cmidnumber', 'S8_MANUAL_PAGE'));
$legacyidnumber = trim((string)cli_value($argv, 'legacy-idnumber', ''));
$legacyfullname = trim((string)cli_value($argv, 'legacy-fullname', ''));
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

function s8_probe_module_by_cmidnumber(stdClass $course, string $cmidnumber): ?array {
    global $DB;
    if ($cmidnumber === '') {
        return null;
    }
    $module = $DB->get_record('modules', ['name' => 'scorm'], 'id,name', MUST_EXIST);
    $cm = $DB->get_record('course_modules', [
        'course' => (int)$course->id,
        'module' => (int)$module->id,
        'idnumber' => $cmidnumber,
    ], '*', IGNORE_MISSING);
    if (!$cm) {
        return null;
    }
    $scorm = $DB->get_record('scorm', ['id' => (int)$cm->instance], '*', IGNORE_MISSING);
    return $scorm ? ['cm' => $cm, 'scorm' => $scorm] : null;
}

function s8_probe_user(string $username, stdClass $course): stdClass {
    global $DB;
    $user = $DB->get_record('user', ['username' => $username, 'deleted' => 0], '*', IGNORE_MISSING);
    if (!$user) {
        $user = create_user_record($username, 'S8_probe_ChangeMe_123!', 'manual');
        $DB->update_record('user', (object)[
            'id' => (int)$user->id,
            'firstname' => 'S8',
            'lastname' => 'Probe',
            'email' => $username . '@example.invalid',
            'confirmed' => 1,
            'timemodified' => time(),
        ]);
        $user = $DB->get_record('user', ['id' => (int)$user->id], '*', MUST_EXIST);
    }
    $student = $DB->get_record('role', ['shortname' => 'student'], 'id,shortname', IGNORE_MISSING);
    enrol_try_internal_enrol((int)$course->id, (int)$user->id, $student ? (int)$student->id : null);
    return $user;
}

function s8_probe_scoes(int $scormid): array {
    global $DB;
    $records = $DB->get_records('scorm_scoes', ['scorm' => $scormid], 'sortorder ASC, id ASC',
        'id,identifier,title,launch,scormtype,sortorder');
    $rows = [];
    foreach ($records as $record) {
        if ((string)($record->scormtype ?? '') !== 'sco') {
            continue;
        }
        $rows[] = [
            'scoid' => (int)$record->id,
            'identifier' => (string)$record->identifier,
            'title' => (string)$record->title,
            'launch' => (string)$record->launch,
            'sortorder' => (int)$record->sortorder,
        ];
    }
    return $rows;
}

function s8_probe_activities(stdClass $section): array {
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

function s8_probe_tracking_snapshot(stdClass $course, stdClass $cm, stdClass $scorm, stdClass $user): array {
    global $DB;
    $tracksql = "SELECT v.id, a.attempt, s.id AS scoid, s.identifier, e.element, v.value, v.timemodified
                   FROM {scorm_attempt} a
                   JOIN {scorm_scoes_value} v ON v.attemptid = a.id
                   JOIN {scorm_scoes} s ON s.id = v.scoid
                   JOIN {scorm_element} e ON e.id = v.elementid
                  WHERE a.userid = :userid AND a.scormid = :scormid
               ORDER BY a.attempt ASC, s.sortorder ASC, e.element ASC";
    $tracks = [];
    foreach ($DB->get_records_sql($tracksql, ['userid' => (int)$user->id, 'scormid' => (int)$scorm->id]) as $row) {
        $tracks[] = [
            'attempt' => (int)$row->attempt,
            'scoid' => (int)$row->scoid,
            'identifier' => (string)$row->identifier,
            'element' => (string)$row->element,
            'value' => (string)$row->value,
        ];
    }
    $gradeitem = $DB->get_record('grade_items', [
        'courseid' => (int)$course->id,
        'itemtype' => 'mod',
        'itemmodule' => 'scorm',
        'iteminstance' => (int)$scorm->id,
    ], '*', IGNORE_MISSING);
    $gradegrade = $gradeitem ? $DB->get_record('grade_grades', ['itemid' => (int)$gradeitem->id, 'userid' => (int)$user->id], '*', IGNORE_MISSING) : false;
    $completion = $DB->get_record('course_modules_completion', ['coursemoduleid' => (int)$cm->id, 'userid' => (int)$user->id], '*', IGNORE_MISSING);
    return [
        'trackedScoIdentifiers' => array_values(array_unique(array_map(fn($row) => $row['identifier'], $tracks))),
        'trackCount' => count($tracks),
        'tracks' => $tracks,
        'gradeItem' => $gradeitem ? ['id' => (int)$gradeitem->id, 'itemname' => (string)$gradeitem->itemname] : null,
        'gradeGrade' => $gradegrade ? ['id' => (int)$gradegrade->id, 'finalgrade' => $gradegrade->finalgrade === null ? null : (float)$gradegrade->finalgrade] : null,
        'completion' => $completion ? ['id' => (int)$completion->id, 'completionstate' => (int)$completion->completionstate] : null,
    ];
}

function s8_probe_draft_file_from_path(string $packagepath): int {
    global $USER;
    if ($packagepath === '' || !is_file($packagepath)) {
        throw new moodle_exception('filenotfound', 'error', '', $packagepath);
    }
    $usercontext = context_user::instance((int)$USER->id);
    $draftid = file_get_unused_draft_itemid();
    get_file_storage()->create_file_from_pathname([
        'component' => 'user',
        'filearea' => 'draft',
        'contextid' => $usercontext->id,
        'itemid' => $draftid,
        'filename' => basename($packagepath),
        'filepath' => '/',
    ], $packagepath);
    return $draftid;
}

function s8_probe_add_duplicate_scorm(stdClass $course, stdClass $section, string $cmidnumber, string $packagepath): array {
    global $CFG;
    [, , , , $data] = prepare_new_moduleinfo_data($course, 'scorm', (int)$section->section);
    $cfgscorm = get_config('scorm');
    $data->name = 'S8 Duplicate Current SCORM Fixture';
    $data->cmidnumber = $cmidnumber;
    $data->introeditor = [
        'text' => '<p>S8 duplicate-current conflict fixture.</p>',
        'format' => FORMAT_HTML,
        'itemid' => file_get_unused_draft_itemid(),
    ];
    $data->scormtype = SCORM_TYPE_LOCAL;
    $data->packagefile = s8_probe_draft_file_from_path($packagepath);
    $data->packageurl = '';
    $data->reference = basename($packagepath);
    $data->version = '';
    $data->maxgrade = is_object($cfgscorm) && isset($cfgscorm->maxgrade) ? $cfgscorm->maxgrade : 100;
    $data->grademethod = is_object($cfgscorm) && isset($cfgscorm->grademethod) ? $cfgscorm->grademethod : GRADESCOES;
    $data->whatgrade = is_object($cfgscorm) && isset($cfgscorm->whatgrade) ? $cfgscorm->whatgrade : HIGHESTATTEMPT;
    $data->maxattempt = is_object($cfgscorm) && isset($cfgscorm->maxattempt) ? $cfgscorm->maxattempt : 1;
    $data->forcecompleted = 0;
    $data->forcenewattempt = SCORM_FORCEATTEMPT_NO;
    $data->lastattemptlock = 0;
    $data->masteryoverride = 1;
    $data->displayattemptstatus = SCORM_DISPLAY_ATTEMPTSTATUS_NO;
    $data->displaycoursestructure = 0;
    $data->updatefreq = SCORM_UPDATE_NEVER;
    $data->sha1hash = sha1_file($packagepath);
    $data->md5hash = md5_file($packagepath);
    $data->revision = 0;
    $data->launch = 0;
    $data->skipview = SCORM_SKIPVIEW_ALWAYS;
    $data->hidebrowse = 1;
    $data->hidetoc = SCORM_TOC_DISABLED;
    $data->nav = SCORM_NAV_DISABLED;
    $data->navpositionleft = -100;
    $data->navpositiontop = -100;
    $data->auto = 0;
    $data->popup = 0;
    $data->options = '';
    $data->width = 100;
    $data->height = 600;
    $data->timeopen = 0;
    $data->timeclose = 0;
    $data->timemodified = time();
    $data->completionstatusrequired = null;
    $data->completionscorerequired = null;
    $data->completionstatusallscos = 0;
    $data->autocommit = 0;
    $data->tags = [];
    $created = add_moduleinfo($data, $course);
    rebuild_course_cache((int)$course->id, true);
    return [
        'cmid' => (int)$created->coursemodule,
        'idnumber' => $cmidnumber,
        'packagePath' => $packagepath,
    ];
}

if ($action === 'manual-page') {
    $module = $DB->get_record('modules', ['name' => 'page'], 'id,name', MUST_EXIST);
    $existing = $DB->get_record('course_modules', ['course' => $courseid, 'module' => (int)$module->id, 'idnumber' => $manualidnumber], '*', IGNORE_MISSING);
    if (!$existing) {
        [, , , , $data] = prepare_new_moduleinfo_data($course, 'page', (int)$section->section);
        $data->name = 'S8 Manual Teacher Page Preserve Fixture';
        $data->cmidnumber = $manualidnumber;
        $data->introeditor = ['text' => '<p>S8 manual page fixture.</p>', 'format' => FORMAT_HTML, 'itemid' => file_get_unused_draft_itemid()];
        $data->content = '<p>This teacher-authored Page must survive S8 rebuild.</p>';
        $data->contentformat = FORMAT_HTML;
        $data->display = 5;
        $data->displayoptions = [];
        add_moduleinfo($data, $course);
        rebuild_course_cache($courseid, true);
    }
}

$target = s8_probe_module_by_cmidnumber($course, $cmidnumber);
$user = s8_probe_user($username, $course);

if ($action === 'seed-history') {
    if (!$target) {
        throw new moodle_exception('invalidrecord', 'error', '', 'Missing SCORM cmidnumber ' . $cmidnumber);
    }
    $scoes = s8_probe_scoes((int)$target['scorm']->id);
    foreach (array_slice($scoes, 0, min(3, count($scoes))) as $index => $sco) {
        $component = preg_replace('/^FLW_[A-Z0-9]+_U\d{3}_/', '', (string)$sco['identifier']);
        scorm_insert_track((int)$user->id, (int)$target['scorm']->id, (int)$sco['scoid'], 1, 'cmi.core.lesson_status', $index === 1 ? 'incomplete' : 'completed');
        scorm_insert_track((int)$user->id, (int)$target['scorm']->id, (int)$sco['scoid'], 1, 'cmi.core.score.raw', (string)(90 - $index));
        scorm_insert_track((int)$user->id, (int)$target['scorm']->id, (int)$sco['scoid'], 1, 'cmi.core.lesson_location', $component . ':stable');
        scorm_insert_track((int)$user->id, (int)$target['scorm']->id, (int)$sco['scoid'], 1, 'cmi.core.session_time', '00:02:34');
        scorm_insert_track((int)$user->id, (int)$target['scorm']->id, (int)$sco['scoid'], 1, 'cmi.suspend_data', json_encode(['ComponentID' => $component, 'state' => 's8'], JSON_UNESCAPED_SLASHES));
    }
    grade_update('mod/scorm', (int)$course->id, 'mod', 'scorm', (int)$target['scorm']->id, 0, [
        (int)$user->id => ['rawgrade' => 91],
    ]);
    $existing = $DB->get_record('course_modules_completion', ['coursemoduleid' => (int)$target['cm']->id, 'userid' => (int)$user->id], '*', IGNORE_MISSING);
    $completion = (object)[
        'coursemoduleid' => (int)$target['cm']->id,
        'userid' => (int)$user->id,
        'completionstate' => COMPLETION_COMPLETE,
        'viewed' => 1,
        'overrideby' => null,
        'timemodified' => time(),
    ];
    if ($existing) {
        $completion->id = (int)$existing->id;
        $DB->update_record('course_modules_completion', $completion);
    } else {
        $DB->insert_record('course_modules_completion', $completion);
    }
}

if ($action === 'duplicate-scorm') {
    if ($cmidnumber === '') {
        throw new moodle_exception('invalidrecord', 'error', '', 'Missing --cmidnumber for duplicate-scorm action.');
    }
    s8_probe_add_duplicate_scorm($course, $section, $cmidnumber, $packagepath);
}

$legacycourse = null;
if ($action === 'legacy-course') {
    $legacyidnumber = $legacyidnumber !== '' ? $legacyidnumber : ('S8_LEGACY_UNIT_COURSE_' . date('YmdHis'));
    $legacyfullname = $legacyfullname !== '' ? $legacyfullname : ('S8 Disposable Test World Unit Legacy Course ' . date('YmdHis'));
    $legacycourse = $DB->get_record('course', ['idnumber' => $legacyidnumber], '*', IGNORE_MISSING);
    if (!$legacycourse) {
        $record = new stdClass();
        $record->fullname = $legacyfullname;
        $record->shortname = substr(preg_replace('/[^A-Za-z0-9_-]+/', '-', $legacyidnumber), 0, 100);
        $record->idnumber = $legacyidnumber;
        $record->category = (int)$course->category;
        $record->summary = '<p>S8 disposable legacy Unit Course fixture. It must be detected and preserved.</p>';
        $record->summaryformat = FORMAT_HTML;
        $record->format = 'topics';
        $record->numsections = 1;
        $record->visible = 0;
        $record->newsitems = 0;
        $record->startdate = time();
        $legacycourse = create_course($record);
    }
}

$section = $DB->get_record('course_sections', ['id' => $sectionid, 'course' => $courseid], '*', MUST_EXIST);
$target = s8_probe_module_by_cmidnumber($course, $cmidnumber);
$report = [
    'status' => 'PASS',
    'action' => $action,
    'timestamp' => date('c'),
    'courseId' => (int)$course->id,
    'sectionId' => (int)$section->id,
    'sectionNumber' => (int)$section->section,
    'cmidnumber' => $cmidnumber,
    'currentScorm' => $target ? [
        'cmid' => (int)$target['cm']->id,
        'scormId' => (int)$target['scorm']->id,
        'name' => (string)$target['scorm']->name,
        'visible' => (int)$target['cm']->visible,
        'scoes' => s8_probe_scoes((int)$target['scorm']->id),
        'tracking' => s8_probe_tracking_snapshot($course, $target['cm'], $target['scorm'], $user),
    ] : null,
    'activities' => s8_probe_activities($section),
    'legacyCourse' => $legacycourse ? [
        'id' => (int)$legacycourse->id,
        'fullname' => (string)$legacycourse->fullname,
        'shortname' => (string)$legacycourse->shortname,
        'idnumber' => (string)$legacycourse->idnumber,
        'category' => (int)$legacycourse->category,
        'visible' => (int)$legacycourse->visible,
    ] : null,
    'user' => ['id' => (int)$user->id, 'username' => (string)$user->username],
];

if ($reportpath !== '') {
    file_put_contents($reportpath, json_out($report));
}
echo json_out($report) . PHP_EOL;
exit(0);
