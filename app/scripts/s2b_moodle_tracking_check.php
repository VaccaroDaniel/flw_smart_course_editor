<?php
// Controlled S2B Moodle integration check for FLW multi-SCO package tracking.
//
// This script creates a temporary hidden Moodle course, imports one SCORM package
// using Moodle's normal module APIs, verifies stable identifier -> numeric scoid
// resolution and per-SCO tracking writes, then removes the temporary course unless
// --keep-course is supplied.

define('CLI_SCRIPT', true);

$options = getopt('', ['moodle-config:', 'zip:', 'keep-course']);
$configpath = $options['moodle-config'] ?? '';
$zippath = $options['zip'] ?? '';

if ($configpath === '' || $zippath === '') {
    fwrite(STDERR, "Usage: php s2b_moodle_tracking_check.php --moodle-config=/path/to/config.php --zip=/path/to/package.zip [--keep-course]\n");
    exit(2);
}
if (!is_file($configpath)) {
    fwrite(STDERR, "Moodle config not found: {$configpath}\n");
    exit(2);
}
if (!is_file($zippath)) {
    fwrite(STDERR, "SCORM package not found: {$zippath}\n");
    exit(2);
}

require($configpath);
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/course/modlib.php');
require_once($CFG->dirroot . '/mod/scorm/lib.php');
require_once($CFG->dirroot . '/mod/scorm/locallib.php');

// The local Windows Moodle installer can fail during ZIP extraction when the
// file pool uses LOCK_EX and immediately renames the temporary hash file. This
// is a per-process test-helper setting; it does not modify Moodle core or
// stored Moodle configuration.
$CFG->preventfilelocking = true;

function s2b_fail(string $message): void {
    throw new RuntimeException($message);
}

function s2b_cfg_value($cfg, string $name, $fallback) {
    return (is_object($cfg) && property_exists($cfg, $name)) ? $cfg->{$name} : $fallback;
}

function s2b_draft_file_from_path(string $path): int {
    global $USER;
    $draftitemid = file_get_unused_draft_itemid();
    $context = context_user::instance($USER->id);
    $fs = get_file_storage();
    $record = [
        'contextid' => $context->id,
        'component' => 'user',
        'filearea' => 'draft',
        'itemid' => $draftitemid,
        'filepath' => '/',
        'filename' => basename($path),
    ];
    $fs->create_file_from_pathname($record, $path);
    return $draftitemid;
}

function s2b_track_value(int $userid, int $scoid, int $attempt, string $element): ?string {
    $track = scorm_get_sco_value($scoid, $userid, $element, $attempt);
    return $track ? (string)$track->value : null;
}

function s2b_assert_track(int $userid, int $scoid, int $attempt, string $element, string $expected): void {
    $actual = s2b_track_value($userid, $scoid, $attempt, $element);
    if ($actual !== $expected) {
        s2b_fail("Expected {$element}={$expected} for scoid {$scoid}; got " . var_export($actual, true));
    }
}

function s2b_prewarm_zip_file_pool(string $zippath, array &$results): void {
    global $CFG;
    $zip = new ZipArchive();
    if ($zip->open($zippath) !== true) {
        s2b_fail('Could not open ZIP for file-pool prewarm: ' . $zippath);
    }
    $filedir = rtrim($CFG->dataroot, '/\\') . '/filedir';
    $created = 0;
    $existing = 0;
    $entries = 0;
    for ($i = 0; $i < $zip->numFiles; $i++) {
        $stat = $zip->statIndex($i);
        $name = $stat['name'] ?? ('entry-' . $i);
        if (str_ends_with($name, '/')) {
            continue;
        }
        $content = $zip->getFromIndex($i);
        if ($content === false) {
            $zip->close();
            s2b_fail('Could not read ZIP entry during file-pool prewarm: ' . $name);
        }
        $entries++;
        $hash = sha1($content);
        $size = strlen($content);
        $hashdir = $filedir . '/' . substr($hash, 0, 2) . '/' . substr($hash, 2, 2);
        $hashfile = $hashdir . '/' . $hash;
        if (is_file($hashfile) && filesize($hashfile) === $size && sha1_file($hashfile) === $hash) {
            $existing++;
            continue;
        }
        if (!is_dir($hashdir) && !mkdir($hashdir, $CFG->directorypermissions ?? 0777, true)) {
            $zip->close();
            s2b_fail('Could not create Moodle file-pool hash directory: ' . $hashdir);
        }
        $tmp = $hashfile . '.tmp';
        @unlink($tmp);
        $ok = false;
        for ($attempt = 1; $attempt <= 8; $attempt++) {
            if (file_put_contents($tmp, $content) === false) {
                usleep(150000);
                continue;
            }
            clearstatcache(true, $tmp);
            if (filesize($tmp) !== $size || sha1_file($tmp) !== $hash) {
                @unlink($tmp);
                usleep(150000);
                continue;
            }
            if (@rename($tmp, $hashfile)) {
                @chmod($hashfile, $CFG->filepermissions ?? 0666);
                $ok = true;
                $created++;
                break;
            }
            @unlink($tmp);
            usleep(200000);
        }
        if (!$ok) {
            $zip->close();
            s2b_fail('Could not prewarm Moodle file-pool content for ZIP entry ' . $name . ' hash ' . $hash);
        }
    }
    $zip->close();
    $results['filePoolPrewarm'] = [
        'entries' => $entries,
        'created' => $created,
        'existing' => $existing,
        'reason' => 'Windows Moodle file-pool extraction rename failed without prewarm in this environment.',
    ];
}

$courseid = 0;
$keepcourse = array_key_exists('keep-course', $options);
$stamp = date('Ymd_His') . '_' . random_int(1000, 9999);
$results = [
    'status' => 'RUNNING',
    'createdCourseId' => null,
    'createdCourseDeleted' => false,
    'moodleRelease' => $CFG->release ?? '',
    'package' => $zippath,
    'checks' => [],
];

try {
    global $DB, $USER;
    $admin = $DB->get_record('user', ['id' => 2, 'deleted' => 0], '*', MUST_EXIST);
    \core\session\manager::set_user($admin);
    $userid = (int)$admin->id;

    $categoryid = $DB->get_field_sql('SELECT MIN(id) FROM {course_categories}');
    if (!$categoryid) {
        s2b_fail('No Moodle course category is available for temporary S2B test course creation.');
    }

    $course = new stdClass();
    $course->fullname = 'FLW S2B Temporary Tracking Check ' . $stamp;
    $course->shortname = 'FLW_S2B_TMP_' . $stamp;
    $course->idnumber = 'FLW_S2B_TMP_' . $stamp;
    $course->category = (int)$categoryid;
    $course->summary = 'Temporary hidden course created by Smart Course Editor S2B tracking check.';
    $course->summaryformat = FORMAT_HTML;
    $course->format = 'topics';
    $course->visible = 0;
    $course->enablecompletion = 1;
    $course = create_course($course);
    $courseid = (int)$course->id;
    $results['createdCourseId'] = $courseid;

    course_create_sections_if_missing($course, 1);
    rebuild_course_cache($courseid, true);
    s2b_prewarm_zip_file_pool($zippath, $results);
    $results['checks']['filePoolPrewarm'] = 'PASS';

    $cfgscorm = get_config('scorm');
    [, , , , $data] = prepare_new_moduleinfo_data($course, 'scorm', 1);
    $data->name = 'FLW S2B Temporary SCORM';
    $data->cmidnumber = 'FLW_S2B_TMP_UNITSCORM_' . $stamp;
    $data->introeditor = [
        'text' => '<p>Temporary S2B SCORM tracking check.</p>',
        'format' => FORMAT_HTML,
        'itemid' => file_get_unused_draft_itemid(),
    ];
    $data->scormtype = SCORM_TYPE_LOCAL;
    $draftitemid = s2b_draft_file_from_path($zippath);
    $results['checks']['draftFileStorage'] = 'PASS';
    $data->packagefile = $draftitemid;
    $data->packageurl = '';
    $data->reference = basename($zippath);
    $data->version = '';
    $data->maxgrade = s2b_cfg_value($cfgscorm, 'maxgrade', 100);
    $data->grademethod = s2b_cfg_value($cfgscorm, 'grademethod', GRADESCOES);
    $data->whatgrade = s2b_cfg_value($cfgscorm, 'whatgrade', HIGHESTATTEMPT);
    $data->maxattempt = s2b_cfg_value($cfgscorm, 'maxattempt', 1);
    $data->forcecompleted = s2b_cfg_value($cfgscorm, 'forcecompleted', 0);
    $data->forcenewattempt = s2b_cfg_value($cfgscorm, 'forcenewattempt', SCORM_FORCEATTEMPT_NO);
    $data->lastattemptlock = s2b_cfg_value($cfgscorm, 'lastattemptlock', 0);
    $data->masteryoverride = s2b_cfg_value($cfgscorm, 'masteryoverride', 1);
    $data->displayattemptstatus = SCORM_DISPLAY_ATTEMPTSTATUS_NO;
    $data->displaycoursestructure = 0;
    $data->updatefreq = SCORM_UPDATE_NEVER;
    $data->sha1hash = sha1_file($zippath);
    $data->md5hash = md5_file($zippath);
    $data->revision = 0;
    $data->launch = 0;
    $data->skipview = SCORM_SKIPVIEW_ALWAYS;
    $data->hidebrowse = 1;
    $data->hidetoc = SCORM_TOC_DISABLED;
    $data->nav = SCORM_NAV_DISABLED;
    $data->navpositionleft = -100;
    $data->navpositiontop = -100;
    $data->auto = s2b_cfg_value($cfgscorm, 'auto', 0);
    $data->popup = 0;
    $data->options = '';
    $data->width = s2b_cfg_value($cfgscorm, 'framewidth', 100);
    $data->height = s2b_cfg_value($cfgscorm, 'frameheight', 600);
    $data->timeopen = 0;
    $data->timeclose = 0;
    $data->timemodified = time();
    $data->completionstatusrequired = null;
    $data->completionscorerequired = null;
    $data->completionstatusallscos = 0;
    $data->autocommit = s2b_cfg_value($cfgscorm, 'autocommit', 0);
    $data->tags = [];

    $moduleinfo = add_moduleinfo($data, $course);
    $cmid = (int)($moduleinfo->coursemodule ?? 0);
    if (!$cmid) {
        $cmid = (int)($moduleinfo->id ?? 0);
    }
    $scorm = $DB->get_record('scorm', ['id' => $moduleinfo->instance], '*', MUST_EXIST);
    $cm = get_coursemodule_from_instance('scorm', $scorm->id, $course->id, false, MUST_EXIST);
    if (!$cmid) {
        $cmid = (int)$cm->id;
    }
    $results['cmid'] = $cmid;
    $results['scormId'] = (int)$scorm->id;
    $results['scormSettings'] = [
        'skipview' => (int)$scorm->skipview,
        'hidetoc' => (int)$scorm->hidetoc,
        'nav' => (int)$scorm->nav,
        'displaycoursestructure' => (int)$scorm->displaycoursestructure,
        'displayattemptstatus' => (int)$scorm->displayattemptstatus,
        'hidebrowse' => (int)$scorm->hidebrowse,
    ];

    $expected = [
        'FLW_REW_U023_VOCAB',
        'FLW_REW_U023_L01',
        'FLW_REW_U023_L02',
        'FLW_REW_U023_L03',
        'FLW_REW_U023_L04',
        'FLW_REW_U023_L05',
        'FLW_REW_U023_L06',
        'FLW_REW_U023_L07',
        'FLW_REW_U023_WATCH',
        'FLW_REW_U023_RESULT',
    ];
    $rows = $DB->get_records_list('scorm_scoes', 'identifier', $expected, 'id ASC', 'id,identifier,title,launch,scorm');
    $byidentifier = [];
    foreach ($rows as $row) {
        $byidentifier[$row->identifier] = $row;
    }
    foreach ($expected as $identifier) {
        if (!isset($byidentifier[$identifier])) {
            s2b_fail("Missing parsed Moodle scorm_scoes row for {$identifier}");
        }
        $launchable = scorm_check_launchable_sco($scorm, (int)$byidentifier[$identifier]->id);
        if ((int)$launchable !== (int)$byidentifier[$identifier]->id) {
            s2b_fail("Moodle did not treat {$identifier} as launchable.");
        }
    }
    $results['stableIdentifierToScoid'] = [];
    foreach ($byidentifier as $identifier => $row) {
        $results['stableIdentifierToScoid'][$identifier] = (int)$row->id;
    }
    $results['parsedScoCount'] = count($byidentifier);
    $results['expectedScoCount'] = count($expected);
    $results['checks']['stableIdentifierResolution'] = 'PASS';

    $attemptsBefore = $DB->count_records('scorm_attempt', ['userid' => $userid, 'scormid' => (int)$scorm->id]);
    $attempt = scorm_get_attempt($userid, (int)$scorm->id, 1, true);
    $attemptno = (int)$attempt->attempt;
    $results['attemptsBeforeWrites'] = $attemptsBefore;
    $results['attemptNumberUsed'] = $attemptno;

    $l1 = (int)$byidentifier['FLW_REW_U023_L01']->id;
    $l2 = (int)$byidentifier['FLW_REW_U023_L02']->id;
    $l3 = (int)$byidentifier['FLW_REW_U023_L03']->id;
    $l4 = (int)$byidentifier['FLW_REW_U023_L04']->id;
    $watch = (int)$byidentifier['FLW_REW_U023_WATCH']->id;

    $tocobject = scorm_get_toc_object($admin, $scorm, '', $l1, 'normal', $attemptno, true, null);
    $results['moodleAdlnav'] = json_decode(scorm_get_adlnav_json($tocobject['scoes']), true);

    scorm_insert_track($userid, (int)$scorm->id, $l1, $attempt, 'cmi.core.lesson_status', 'completed');
    scorm_insert_track($userid, (int)$scorm->id, $l1, $attempt, 'cmi.core.score.raw', '91');
    scorm_insert_track($userid, (int)$scorm->id, $l1, $attempt, 'cmi.core.lesson_location', 'REW-U023-L01');
    scorm_insert_track($userid, (int)$scorm->id, $l1, $attempt, 'cmi.suspend_data', '{"schemaVersion":1,"lastComponentId":"REW-U023-L01"}');

    scorm_insert_track($userid, (int)$scorm->id, $l2, $attempt, 'cmi.core.lesson_status', 'incomplete');
    scorm_insert_track($userid, (int)$scorm->id, $l2, $attempt, 'cmi.core.score.raw', '22');
    scorm_insert_track($userid, (int)$scorm->id, $l2, $attempt, 'cmi.core.lesson_location', 'REW-U023-L02');
    scorm_insert_track($userid, (int)$scorm->id, $l2, $attempt, 'cmi.suspend_data', '{"schemaVersion":1,"lastComponentId":"REW-U023-L02"}');

    s2b_assert_track($userid, $l1, $attemptno, 'cmi.core.lesson_status', 'completed');
    s2b_assert_track($userid, $l1, $attemptno, 'cmi.core.score.raw', '91');
    s2b_assert_track($userid, $l1, $attemptno, 'cmi.core.lesson_location', 'REW-U023-L01');
    s2b_assert_track($userid, $l2, $attemptno, 'cmi.core.lesson_status', 'incomplete');
    s2b_assert_track($userid, $l2, $attemptno, 'cmi.core.score.raw', '22');
    s2b_assert_track($userid, $l2, $attemptno, 'cmi.core.lesson_location', 'REW-U023-L02');
    $results['checks']['testA_lesson1Lesson2TrackingIsolation'] = 'PASS';
    $results['checks']['testD_lesson2NotFalselyCompleted'] = 'PASS';

    scorm_insert_track($userid, (int)$scorm->id, $watch, $attempt, 'cmi.core.lesson_status', 'completed');
    scorm_insert_track($userid, (int)$scorm->id, $watch, $attempt, 'cmi.core.score.raw', '88');
    scorm_insert_track($userid, (int)$scorm->id, $watch, $attempt, 'cmi.core.lesson_location', 'REW-U023-WATCH');
    s2b_assert_track($userid, $watch, $attemptno, 'cmi.core.lesson_location', 'REW-U023-WATCH');
    s2b_assert_track($userid, $watch, $attemptno, 'cmi.core.score.raw', '88');
    $results['checks']['testB_watchTrackingIsolation'] = 'PASS';

    scorm_insert_track($userid, (int)$scorm->id, $l3, $attempt, 'cmi.core.lesson_status', 'incomplete');
    scorm_insert_track($userid, (int)$scorm->id, $l3, $attempt, 'cmi.core.lesson_location', 'REW-U023-L03');
    scorm_insert_track($userid, (int)$scorm->id, $l2, $attempt, 'cmi.core.lesson_location', 'REW-U023-L02');
    s2b_assert_track($userid, $l3, $attemptno, 'cmi.core.lesson_location', 'REW-U023-L03');
    s2b_assert_track($userid, $l2, $attemptno, 'cmi.core.lesson_location', 'REW-U023-L02');
    $results['checks']['testC_previousTrackingIsolation'] = 'PASS';

    scorm_insert_track($userid, (int)$scorm->id, $l4, $attempt, 'cmi.core.lesson_status', 'incomplete');
    scorm_insert_track($userid, (int)$scorm->id, $l4, $attempt, 'cmi.core.lesson_location', 'REW-U023-L04');
    scorm_insert_track($userid, (int)$scorm->id, $l4, $attempt, 'cmi.suspend_data', '{"schemaVersion":1,"lastComponentId":"REW-U023-L04"}');
    s2b_assert_track($userid, $l4, $attemptno, 'cmi.core.lesson_location', 'REW-U023-L04');
    s2b_assert_track($userid, $l4, $attemptno, 'cmi.suspend_data', '{"schemaVersion":1,"lastComponentId":"REW-U023-L04"}');
    $results['checks']['testE_resumeStorageContract'] = 'PASS';
    $results['attemptsAfterWrites'] = $DB->count_records('scorm_attempt', ['userid' => $userid, 'scormid' => (int)$scorm->id]);
    if ($results['attemptsAfterWrites'] !== 1) {
        s2b_fail('Unexpected SCORM attempt count after component navigation/tracking writes: ' . $results['attemptsAfterWrites']);
    }
    $results['checks']['attemptsStayInOneMoodleAttempt'] = 'PASS';

    $results['playerLaunchUrls'] = [
        'L02' => $CFG->wwwroot . '/mod/scorm/player.php?cm=' . $cmid . '&scoid=' . $l2,
        'WATCH' => $CFG->wwwroot . '/mod/scorm/player.php?cm=' . $cmid . '&scoid=' . $watch,
    ];
    $results['status'] = 'PASS';
} catch (Throwable $e) {
    try {
        if (isset($DB)) {
            $DB->force_transaction_rollback();
        }
    } catch (Throwable $rollback) {
        $results['rollbackError'] = $rollback->getMessage();
    }
    $results['status'] = 'FAIL';
    $results['error'] = $e->getMessage();
    $results['errorClass'] = get_class($e);
    $results['errorFile'] = $e->getFile();
    $results['errorLine'] = $e->getLine();
    $results['errorTrace'] = $e->getTraceAsString();
} finally {
    if ($courseid && !$keepcourse) {
        try {
            delete_course($courseid, false);
            $results['createdCourseDeleted'] = true;
        } catch (Throwable $cleanup) {
            $results['cleanupError'] = $cleanup->getMessage();
        }
    }
}

echo json_encode($results, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL;
exit($results['status'] === 'PASS' ? 0 : 1);
