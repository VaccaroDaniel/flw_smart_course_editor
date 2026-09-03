<?php
// S5 verification helper: seed/snapshot SCORM 1.2 tracking using Moodle APIs.

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
require_once($CFG->libdir . '/moodlelib.php');
require_once($CFG->libdir . '/enrollib.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/mod/scorm/lib.php');
require_once($CFG->dirroot . '/mod/scorm/locallib.php');

global $argv, $DB, $USER, $CFG;

$action = cli_value($argv, 'action', 'snapshot');
$courseid = (int)cli_value($argv, 'courseid', '200');
$cmidnumber = cli_value($argv, 'cmidnumber', 'FLW_REW_U023_UNITSCORM');
$username = strtolower(trim((string)cli_value($argv, 'username', 's5_learner_rew_u023')));
$reportpath = cli_value($argv, 'report', '');
$moodleurl = trim((string)cli_value($argv, 'moodle-url', ''));
if ($moodleurl !== '') {
    $CFG->wwwroot = rtrim($moodleurl, '/');
}

$actor = get_admin();
\core\session\manager::set_user($actor);
$USER = $actor;

$module = $DB->get_record('modules', ['name' => 'scorm'], 'id,name', MUST_EXIST);
$cm = $DB->get_record('course_modules', ['course' => $courseid, 'module' => $module->id, 'idnumber' => $cmidnumber], '*', MUST_EXIST);
$scorm = $DB->get_record('scorm', ['id' => (int)$cm->instance], '*', MUST_EXIST);
$course = $DB->get_record('course', ['id' => $courseid], '*', MUST_EXIST);

function ensure_probe_user(string $username, stdClass $course): stdClass {
    global $DB;

    $user = $DB->get_record('user', ['username' => $username, 'deleted' => 0], '*', IGNORE_MISSING);
    if (!$user) {
        $user = create_user_record($username, 'S5_probe_ChangeMe_123!', 'manual');
        $update = (object)[
            'id' => (int)$user->id,
            'firstname' => 'S5',
            'lastname' => 'Learner',
            'email' => $username . '@example.invalid',
            'confirmed' => 1,
            'timemodified' => time(),
        ];
        $DB->update_record('user', $update);
        $user = $DB->get_record('user', ['id' => (int)$user->id], '*', MUST_EXIST);
    }
    $student = $DB->get_record('role', ['shortname' => 'student'], 'id,shortname', IGNORE_MISSING);
    enrol_try_internal_enrol((int)$course->id, (int)$user->id, $student ? (int)$student->id : null);
    return $user;
}

function launch_sco_map(int $scormid): array {
    global $DB;

    $records = $DB->get_records('scorm_scoes', ['scorm' => $scormid], 'sortorder ASC, id ASC',
        'id,identifier,title,launch,scormtype,sortorder');
    $rows = [];
    foreach ($records as $record) {
        if ((string)($record->scormtype ?? '') !== 'sco') {
            continue;
        }
        $rows[(string)$record->identifier] = [
            'scoid' => (int)$record->id,
            'identifier' => (string)$record->identifier,
            'title' => (string)$record->title,
            'launch' => (string)$record->launch,
            'sortorder' => (int)$record->sortorder,
        ];
    }
    return $rows;
}

function tracking_snapshot(stdClass $course, stdClass $cm, stdClass $scorm, stdClass $user): array {
    global $DB, $CFG;

    $scoes = launch_sco_map((int)$scorm->id);
    $attempts = $DB->get_records('scorm_attempt', ['userid' => (int)$user->id, 'scormid' => (int)$scorm->id], 'attempt ASC, id ASC');
    $tracksql = "SELECT v.id, a.attempt, s.id AS scoid, s.identifier, e.element, v.value, v.timemodified
                   FROM {scorm_attempt} a
                   JOIN {scorm_scoes_value} v ON v.attemptid = a.id
                   JOIN {scorm_scoes} s ON s.id = v.scoid
                   JOIN {scorm_element} e ON e.id = v.elementid
                  WHERE a.userid = :userid AND a.scormid = :scormid
               ORDER BY a.attempt ASC, s.sortorder ASC, e.element ASC";
    $trackrows = [];
    foreach ($DB->get_records_sql($tracksql, ['userid' => (int)$user->id, 'scormid' => (int)$scorm->id]) as $row) {
        $trackrows[] = [
            'attempt' => (int)$row->attempt,
            'scoid' => (int)$row->scoid,
            'identifier' => (string)$row->identifier,
            'element' => (string)$row->element,
            'value' => (string)$row->value,
            'timemodified' => (int)$row->timemodified,
        ];
    }
    $gradeitem = $DB->get_record('grade_items', [
        'courseid' => (int)$course->id,
        'itemtype' => 'mod',
        'itemmodule' => 'scorm',
        'iteminstance' => (int)$scorm->id,
    ], '*', IGNORE_MISSING);
    $gradegrade = $gradeitem ? $DB->get_record('grade_grades', [
        'itemid' => (int)$gradeitem->id,
        'userid' => (int)$user->id,
    ], '*', IGNORE_MISSING) : false;
    $completion = $DB->get_record('course_modules_completion', [
        'coursemoduleid' => (int)$cm->id,
        'userid' => (int)$user->id,
    ], '*', IGNORE_MISSING);

    return [
        'courseId' => (int)$course->id,
        'cmid' => (int)$cm->id,
        'scormId' => (int)$scorm->id,
        'cmidnumber' => (string)$cm->idnumber,
        'scormName' => (string)$scorm->name,
        'scormRevision' => (int)$scorm->revision,
        'scormSha1hash' => (string)$scorm->sha1hash,
        'viewUrl' => rtrim((string)$CFG->wwwroot, '/') . '/mod/scorm/view.php?id=' . (int)$cm->id,
        'user' => [
            'id' => (int)$user->id,
            'username' => (string)$user->username,
        ],
        'scoes' => array_values($scoes),
        'attempts' => array_values(array_map(fn($attempt) => [
            'id' => (int)$attempt->id,
            'attempt' => (int)$attempt->attempt,
            'userid' => (int)$attempt->userid,
        ], $attempts)),
        'tracks' => $trackrows,
        'trackedScoIdentifiers' => array_values(array_unique(array_map(fn($row) => $row['identifier'], $trackrows))),
        'gradeItem' => $gradeitem ? [
            'id' => (int)$gradeitem->id,
            'itemname' => (string)$gradeitem->itemname,
            'grademax' => (float)$gradeitem->grademax,
            'gradepass' => (float)$gradeitem->gradepass,
        ] : null,
        'gradeGrade' => $gradegrade ? [
            'id' => (int)$gradegrade->id,
            'finalgrade' => $gradegrade->finalgrade === null ? null : (float)$gradegrade->finalgrade,
            'rawgrade' => $gradegrade->rawgrade === null ? null : (float)$gradegrade->rawgrade,
        ] : null,
        'completion' => $completion ? [
            'id' => (int)$completion->id,
            'completionstate' => (int)$completion->completionstate,
        ] : null,
    ];
}

$user = ensure_probe_user($username, $course);

if ($action === 'seed') {
    $scoes = launch_sco_map((int)$scorm->id);
    $seed = [
        'FLW_REW_U023_L01' => ['status' => 'completed', 'score' => '95', 'location' => 'REW-U023-L01:stable', 'suspend' => '{"ComponentID":"REW-U023-L01","state":"done"}'],
        'FLW_REW_U023_L02' => ['status' => 'incomplete', 'score' => '72', 'location' => 'REW-U023-L02:stable', 'suspend' => '{"ComponentID":"REW-U023-L02","state":"mid"}'],
        'FLW_REW_U023_WATCH' => ['status' => 'completed', 'score' => '88', 'location' => 'REW-U023-WATCH:stable', 'suspend' => '{"ComponentID":"REW-U023-WATCH","state":"done"}'],
    ];
    foreach ($seed as $identifier => $values) {
        if (empty($scoes[$identifier])) {
            throw new moodle_exception('invalidrecord', 'error', '', 'Missing SCO identifier ' . $identifier);
        }
        $scoid = (int)$scoes[$identifier]['scoid'];
        scorm_insert_track((int)$user->id, (int)$scorm->id, $scoid, 1, 'cmi.core.lesson_status', $values['status']);
        scorm_insert_track((int)$user->id, (int)$scorm->id, $scoid, 1, 'cmi.core.score.raw', $values['score']);
        scorm_insert_track((int)$user->id, (int)$scorm->id, $scoid, 1, 'cmi.core.lesson_location', $values['location']);
        scorm_insert_track((int)$user->id, (int)$scorm->id, $scoid, 1, 'cmi.core.session_time', '00:03:21');
        scorm_insert_track((int)$user->id, (int)$scorm->id, $scoid, 1, 'cmi.suspend_data', $values['suspend']);
    }
}

$report = [
    'status' => 'PASS',
    'action' => $action,
    'timestamp' => date('c'),
    'snapshot' => tracking_snapshot($course, $cm, $scorm, $user),
];

if ($reportpath !== '') {
    file_put_contents($reportpath, json_out($report));
}
echo json_out($report) . PHP_EOL;
exit(0);
