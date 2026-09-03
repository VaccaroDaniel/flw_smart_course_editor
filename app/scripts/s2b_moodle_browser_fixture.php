<?php
// S2B browser-player fixture.
//
// Creates a visible disposable Moodle course, a disposable enrolled test user,
// and imports one SCORM package through Moodle's normal module APIs. It writes
// no SCORM tracking rows; browser/player verification should create tracking.

define('CLI_SCRIPT', true);

$options = getopt('', ['moodle-config:', 'zip:']);
$configpath = $options['moodle-config'] ?? '';
$zippath = $options['zip'] ?? '';

if ($configpath === '' || $zippath === '') {
    fwrite(STDERR, "Usage: php s2b_moodle_browser_fixture.php --moodle-config=/path/to/config.php --zip=/path/to/package.zip\n");
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
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->dirroot . '/enrol/manual/lib.php');

$CFG->preventfilelocking = true;

function s2b_browser_fail(string $message): void {
    throw new RuntimeException($message);
}

function s2b_browser_cfg_value($cfg, string $name, $fallback) {
    return (is_object($cfg) && property_exists($cfg, $name)) ? $cfg->{$name} : $fallback;
}

function s2b_browser_prewarm_file_pool_content(string $content, string $label): string {
    global $CFG;
    $filedir = rtrim($CFG->dataroot, '/\\') . '/filedir';
    $hash = sha1($content);
    $size = strlen($content);
    $hashdir = $filedir . '/' . substr($hash, 0, 2) . '/' . substr($hash, 2, 2);
    $hashfile = $hashdir . '/' . $hash;
    if (is_file($hashfile) && filesize($hashfile) === $size && sha1_file($hashfile) === $hash) {
        return $hash;
    }
    if (!is_dir($hashdir) && !mkdir($hashdir, $CFG->directorypermissions ?? 0777, true)) {
        s2b_browser_fail('Could not create Moodle file-pool hash directory for ' . $label . ': ' . $hashdir);
    }
    $tmp = $hashfile . '.tmp.' . getmypid() . '.' . random_int(1000, 9999);
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
            break;
        }
        if (is_file($hashfile) && filesize($hashfile) === $size && sha1_file($hashfile) === $hash) {
            $ok = true;
            break;
        }
        @unlink($tmp);
        usleep(200000);
    }
    if (!$ok) {
        @unlink($tmp);
        s2b_browser_fail('Could not prewarm Moodle file-pool content for ' . $label . ' hash ' . $hash);
    }
    return $hash;
}

function s2b_browser_prewarm_path_file_pool(string $path): string {
    $content = file_get_contents($path);
    if ($content === false) {
        s2b_browser_fail('Could not read file for file-pool prewarm: ' . $path);
    }
    return s2b_browser_prewarm_file_pool_content($content, basename($path));
}

function s2b_browser_draft_file_from_path(string $path): int {
    global $USER;
    s2b_browser_prewarm_path_file_pool($path);
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

function s2b_browser_prewarm_zip_file_pool(string $zippath): array {
    global $CFG;
    $zip = new ZipArchive();
    if ($zip->open($zippath) !== true) {
        s2b_browser_fail('Could not open ZIP for file-pool prewarm: ' . $zippath);
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
            s2b_browser_fail('Could not read ZIP entry during file-pool prewarm: ' . $name);
        }
        $entries++;
        $hash = sha1($content);
        $hashfile = $filedir . '/' . substr($hash, 0, 2) . '/' . substr($hash, 2, 2) . '/' . $hash;
        if (is_file($hashfile) && filesize($hashfile) === strlen($content) && sha1_file($hashfile) === $hash) {
            $existing++;
            continue;
        }
        s2b_browser_prewarm_file_pool_content($content, 'ZIP entry ' . $name);
        $created++;
    }
    $zip->close();
    return [
        'entries' => $entries,
        'created' => $created,
        'existing' => $existing,
    ];
}

function s2b_browser_enrol_user(stdClass $course, int $userid): array {
    global $DB;
    $manual = enrol_get_plugin('manual');
    if (!$manual) {
        s2b_browser_fail('Manual enrolment plugin is not available.');
    }
    $instances = enrol_get_instances($course->id, true);
    $manualinstance = null;
    foreach ($instances as $instance) {
        if ($instance->enrol === 'manual') {
            $manualinstance = $instance;
            break;
        }
    }
    if (!$manualinstance) {
        $instanceid = $manual->add_default_instance($course);
        if (!$instanceid) {
            $instanceid = $manual->add_instance($course);
        }
        $manualinstance = $DB->get_record('enrol', ['id' => $instanceid], '*', MUST_EXIST);
    }
    $roleid = (int)$DB->get_field('role', 'id', ['shortname' => 'student'], MUST_EXIST);
    $manual->enrol_user($manualinstance, $userid, $roleid, time(), 0, ENROL_USER_ACTIVE);
    return [
        'enrolInstanceId' => (int)$manualinstance->id,
        'roleId' => $roleid,
    ];
}

$courseid = 0;
$userid = 0;
$result = [
    'status' => 'RUNNING',
    'moodleRelease' => '',
    'wwwroot' => '',
    'package' => $zippath,
    'createdCourseId' => null,
    'createdUserId' => null,
    'createdCourseDeleted' => false,
    'createdUserDeleted' => false,
];

try {
    global $CFG, $DB, $USER;
    $result['moodleRelease'] = $CFG->release ?? '';
    $result['wwwroot'] = $CFG->wwwroot ?? '';

    $admin = $DB->get_record('user', ['id' => 2, 'deleted' => 0], '*', MUST_EXIST);
    \core\session\manager::set_user($admin);

    $stamp = date('Ymd_His') . '_' . random_int(1000, 9999);
    $username = 's2b_browser_' . strtolower($stamp);
    $password = 'S2B!' . $stamp . 'Aa9$';

    $categoryid = $DB->get_field_sql('SELECT MIN(id) FROM {course_categories}');
    if (!$categoryid) {
        s2b_browser_fail('No Moodle course category is available for temporary S2B browser test course creation.');
    }

    $course = new stdClass();
    $course->fullname = 'FLW S2B Browser Player Check ' . $stamp;
    $course->shortname = 'FLW_S2B_BROWSER_TMP_' . $stamp;
    $course->idnumber = 'FLW_S2B_BROWSER_TMP_' . $stamp;
    $course->category = (int)$categoryid;
    $course->summary = 'Temporary visible course created by Smart Course Editor S2B browser/player check.';
    $course->summaryformat = FORMAT_HTML;
    $course->format = 'topics';
    $course->visible = 1;
    $course->enablecompletion = 1;
    $course = create_course($course);
    $courseid = (int)$course->id;
    $result['createdCourseId'] = $courseid;

    $user = new stdClass();
    $user->auth = 'manual';
    $user->confirmed = 1;
    $user->deleted = 0;
    $user->suspended = 0;
    $user->mnethostid = $CFG->mnet_localhost_id;
    $user->username = $username;
    $user->password = $password;
    $user->firstname = 'S2B';
    $user->lastname = 'Browser';
    $user->email = $username . '@example.invalid';
    $user->city = 'Local';
    $user->country = 'US';
    $user->timezone = '99';
    $user->lang = current_language();
    $userid = user_create_user($user, true, false);
    $result['createdUserId'] = $userid;
    $result['username'] = $username;
    $result['password'] = $password;

    $result['enrolment'] = s2b_browser_enrol_user($course, $userid);

    course_create_sections_if_missing($course, 1);
    rebuild_course_cache($courseid, true);
    $result['filePoolPrewarm'] = s2b_browser_prewarm_zip_file_pool($zippath);

    $cfgscorm = get_config('scorm');
    [, , , , $data] = prepare_new_moduleinfo_data($course, 'scorm', 1);
    $data->name = 'FLW S2B Browser SCORM';
    $data->cmidnumber = 'FLW_S2B_BROWSER_SCORM_' . $stamp;
    $data->introeditor = [
        'text' => '<p>Temporary S2B browser/player verification SCORM.</p>',
        'format' => FORMAT_HTML,
        'itemid' => file_get_unused_draft_itemid(),
    ];
    $data->scormtype = SCORM_TYPE_LOCAL;
    $data->packagefile = s2b_browser_draft_file_from_path($zippath);
    $data->packageurl = '';
    $data->reference = basename($zippath);
    $data->version = '';
    $data->maxgrade = s2b_browser_cfg_value($cfgscorm, 'maxgrade', 100);
    $data->grademethod = s2b_browser_cfg_value($cfgscorm, 'grademethod', GRADESCOES);
    $data->whatgrade = s2b_browser_cfg_value($cfgscorm, 'whatgrade', HIGHESTATTEMPT);
    $data->maxattempt = s2b_browser_cfg_value($cfgscorm, 'maxattempt', 1);
    $data->forcecompleted = s2b_browser_cfg_value($cfgscorm, 'forcecompleted', 0);
    $data->forcenewattempt = s2b_browser_cfg_value($cfgscorm, 'forcenewattempt', SCORM_FORCEATTEMPT_NO);
    $data->lastattemptlock = s2b_browser_cfg_value($cfgscorm, 'lastattemptlock', 0);
    $data->masteryoverride = s2b_browser_cfg_value($cfgscorm, 'masteryoverride', 1);
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
    $data->auto = s2b_browser_cfg_value($cfgscorm, 'auto', 0);
    $data->popup = 0;
    $data->options = '';
    $data->width = s2b_browser_cfg_value($cfgscorm, 'framewidth', 100);
    $data->height = s2b_browser_cfg_value($cfgscorm, 'frameheight', 600);
    $data->timeopen = 0;
    $data->timeclose = 0;
    $data->timemodified = time();
    $data->completionstatusrequired = null;
    $data->completionscorerequired = null;
    $data->completionstatusallscos = 0;
    $data->autocommit = s2b_browser_cfg_value($cfgscorm, 'autocommit', 0);
    $data->tags = [];

    $moduleinfo = add_moduleinfo($data, $course);
    $scorm = $DB->get_record('scorm', ['id' => $moduleinfo->instance], '*', MUST_EXIST);
    $cm = get_coursemodule_from_instance('scorm', $scorm->id, $course->id, false, MUST_EXIST);
    $result['cmid'] = (int)$cm->id;
    $result['scormId'] = (int)$scorm->id;
    $result['courseUrl'] = $CFG->wwwroot . '/course/view.php?id=' . $courseid;
    $result['activityViewUrl'] = $CFG->wwwroot . '/mod/scorm/view.php?id=' . (int)$cm->id;

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
            s2b_browser_fail("Missing parsed Moodle scorm_scoes row for {$identifier}");
        }
    }
    $result['stableIdentifierToScoid'] = [];
    $result['launchUrls'] = [];
    foreach ($expected as $identifier) {
        $scoid = (int)$byidentifier[$identifier]->id;
        $result['stableIdentifierToScoid'][$identifier] = $scoid;
        $result['launchUrls'][$identifier] = $CFG->wwwroot . '/mod/scorm/player.php?cm=' . (int)$cm->id . '&scoid=' . $scoid;
    }
    $tocobject = scorm_get_toc_object($admin, $scorm, '', (int)$byidentifier['FLW_REW_U023_L01']->id, 'normal', 1, true, null);
    $result['moodleAdlnav'] = json_decode(scorm_get_adlnav_json($tocobject['scoes']), true);
    $result['scormSettings'] = [
        'skipview' => (int)$scorm->skipview,
        'hidetoc' => (int)$scorm->hidetoc,
        'nav' => (int)$scorm->nav,
        'displaycoursestructure' => (int)$scorm->displaycoursestructure,
        'displayattemptstatus' => (int)$scorm->displayattemptstatus,
        'hidebrowse' => (int)$scorm->hidebrowse,
    ];
    $result['parsedScoCount'] = count($byidentifier);
    $result['expectedScoCount'] = count($expected);
    $result['status'] = 'PASS';
} catch (Throwable $e) {
    $result['status'] = 'FAIL';
    $result['error'] = $e->getMessage();
    $result['errorClass'] = get_class($e);
    $result['errorFile'] = $e->getFile();
    $result['errorLine'] = $e->getLine();
    $result['errorTrace'] = $e->getTraceAsString();
    if ($courseid) {
        try {
            delete_course($courseid, false);
            $result['createdCourseDeleted'] = true;
        } catch (Throwable $cleanup) {
            $result['cleanupError'] = $cleanup->getMessage();
        }
    }
    if ($userid) {
        try {
            delete_user($DB->get_record('user', ['id' => $userid], '*', MUST_EXIST));
            $result['createdUserDeleted'] = true;
        } catch (Throwable $cleanup) {
            $result['userCleanupError'] = $cleanup->getMessage();
        }
    }
}

echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL;
exit($result['status'] === 'PASS' ? 0 : 1);
