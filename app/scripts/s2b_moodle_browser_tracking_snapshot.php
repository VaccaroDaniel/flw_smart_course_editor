<?php
// Read SCORM tracking rows for an S2B browser-player fixture.

define('CLI_SCRIPT', true);

$options = getopt('', ['moodle-config:', 'scorm-id:', 'user-id:']);
$configpath = $options['moodle-config'] ?? '';
$scormid = (int)($options['scorm-id'] ?? 0);
$userid = (int)($options['user-id'] ?? 0);

if ($configpath === '' || !$scormid || !$userid || !is_file($configpath)) {
    fwrite(STDERR, "Usage: php s2b_moodle_browser_tracking_snapshot.php --moodle-config=/path/to/config.php --scorm-id=ID --user-id=ID\n");
    exit(2);
}

require($configpath);
require_once($CFG->dirroot . '/mod/scorm/lib.php');
require_once($CFG->dirroot . '/mod/scorm/locallib.php');

global $DB;

$scorm = $DB->get_record('scorm', ['id' => $scormid], '*', MUST_EXIST);
$cm = get_coursemodule_from_instance('scorm', $scorm->id, $scorm->course, false, MUST_EXIST);
$scoes = $DB->get_records('scorm_scoes', ['scorm' => $scormid], 'id ASC', 'id,identifier,title,launch,scorm');
$attempts = $DB->get_records('scorm_attempt', ['scormid' => $scormid, 'userid' => $userid], 'attempt ASC', '*');
$trackrows = [];
$trackstorage = '';

if ($DB->get_manager()->table_exists('scorm_scoes_track')) {
    $trackstorage = 'scorm_scoes_track';
    $tracks = $DB->get_records('scorm_scoes_track', ['scormid' => $scormid, 'userid' => $userid], 'scoid ASC, attempt ASC, element ASC', '*');
    foreach ($tracks as $track) {
        $trackrows[] = (object)[
            'id' => (int)$track->id,
            'scoid' => (int)$track->scoid,
            'attempt' => (int)$track->attempt,
            'element' => $track->element,
            'value' => (string)$track->value,
            'timemodified' => (int)$track->timemodified,
        ];
    }
} else {
    $trackstorage = 'scorm_scoes_value';
    if ($attempts) {
        [$attemptsql, $attemptparams] = $DB->get_in_or_equal(array_keys($attempts), SQL_PARAMS_NAMED, 'attemptid');
        $trackrows = array_values($DB->get_records_sql(
            "SELECT v.id,
                    v.scoid,
                    a.attempt,
                    e.element,
                    v.value,
                    v.timemodified
               FROM {scorm_scoes_value} v
               JOIN {scorm_attempt} a ON a.id = v.attemptid
               JOIN {scorm_element} e ON e.id = v.elementid
              WHERE v.attemptid {$attemptsql}
           ORDER BY v.scoid ASC, a.attempt ASC, e.element ASC",
            $attemptparams
        ));
    }
}

$byid = [];
foreach ($scoes as $sco) {
    $byid[(int)$sco->id] = [
        'id' => (int)$sco->id,
        'identifier' => $sco->identifier,
        'title' => $sco->title,
        'launch' => $sco->launch,
        'tracks' => [],
    ];
}
foreach ($trackrows as $track) {
    $scoid = (int)$track->scoid;
    if (!isset($byid[$scoid])) {
        $byid[$scoid] = [
            'id' => $scoid,
            'identifier' => '',
            'title' => '',
            'launch' => '',
            'tracks' => [],
        ];
    }
    $attempt = (string)$track->attempt;
    if (!isset($byid[$scoid]['tracks'][$attempt])) {
        $byid[$scoid]['tracks'][$attempt] = [];
    }
    $byid[$scoid]['tracks'][$attempt][$track->element] = (string)$track->value;
}

$last = null;
foreach ($trackrows as $track) {
    if (!in_array($track->element, ['cmi.core.lesson_location', 'cmi.suspend_data'], true)) {
        continue;
    }
    if (!$last || (int)$track->timemodified > (int)$last->timemodified || ((int)$track->timemodified === (int)$last->timemodified && (int)$track->id > (int)$last->id)) {
        $last = $track;
    }
}

echo json_encode([
    'status' => 'PASS',
    'wwwroot' => $CFG->wwwroot,
    'cmid' => (int)$cm->id,
    'scormId' => $scormid,
    'userId' => $userid,
    'trackStorage' => $trackstorage,
    'attempts' => array_map(function($attempt) {
        return [
            'id' => (int)$attempt->id,
            'attempt' => (int)$attempt->attempt,
            'userid' => (int)$attempt->userid,
            'scormid' => (int)$attempt->scormid,
        ];
    }, array_values($attempts)),
    'scoes' => array_values($byid),
    'lastLocationOrSuspendDataWrite' => $last ? [
        'scoid' => (int)$last->scoid,
        'attempt' => (int)$last->attempt,
        'element' => $last->element,
        'value' => (string)$last->value,
        'timemodified' => (int)$last->timemodified,
    ] : null,
], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL;
