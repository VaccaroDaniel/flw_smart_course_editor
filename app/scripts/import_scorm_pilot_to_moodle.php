<?php
// Import SCORM packages produced by scripts/pilot_export_scorm.py into a Moodle course.
//
// This script deliberately uses Moodle's normal module APIs:
// - user draft file area for the ZIP upload
// - add_moduleinfo()
// - mod/scorm's scorm_add_instance() and scorm_parse()

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

function cli_flag(array $argv, string $name): bool {
    return in_array('--' . $name, $argv, true);
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
require_once($CFG->dirroot . '/mod/scorm/lib.php');
require_once($CFG->dirroot . '/mod/scorm/locallib.php');

const MOODLE_COURSE_ID_FLOOR = 200;

function json_out($value): string {
    return json_encode($value, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
}

function cfg_value($cfg, string $field, $default) {
    return (is_object($cfg) && property_exists($cfg, $field) && $cfg->$field !== null) ? $cfg->$field : $default;
}

function clean_short_text($value, int $limit = 255): string {
    $text = trim(preg_replace('/\s+/u', ' ', (string)($value ?? '')));
    if ($text === '') {
        return '';
    }
    if (function_exists('core_text::strlen') && core_text::strlen($text) > $limit) {
        return core_text::substr($text, 0, $limit - 1) . '…';
    }
    if (strlen($text) > ($limit * 4)) {
        return substr($text, 0, $limit * 4);
    }
    return $text;
}

function clean_moodle_url($value): string {
    $raw = trim((string)($value ?? ''));
    if ($raw === '') {
        return '';
    }
    if (!preg_match('/^[A-Za-z][A-Za-z0-9+.-]*:\/\//', $raw)) {
        $raw = 'https://' . $raw;
    }
    $parts = parse_url($raw);
    if (!$parts || empty($parts['scheme']) || empty($parts['host']) || !in_array(strtolower($parts['scheme']), ['http', 'https'], true)) {
        throw new moodle_exception('invalidurl', 'error', '', $value);
    }
    return rtrim($raw, '/');
}

function make_idnumber(array $item, string $stamp): string {
    $raw = 'flw_scorm_pilot_' . ($item['code'] ?? 'unit') . '_u' . ($item['unit'] ?? '001') . '_' . $stamp;
    $clean = strtolower(preg_replace('/[^A-Za-z0-9_]+/', '_', $raw));
    $clean = trim($clean, '_');
    return substr($clean ?: ('flw_scorm_pilot_' . $stamp), 0, 100);
}

function draft_file_from_path(string $packagepath): int {
    global $USER;

    if (!file_exists($packagepath) || !is_file($packagepath)) {
        throw new moodle_exception('filenotfound', 'error', '', $packagepath);
    }
    // S2B/S5 Windows safeguard: Moodle's file API may fail when it has to
    // materialize a new contenthash directly from a user draft upload while a
    // stale *.tmp file exists in filedir. Seeding the package ZIP itself first
    // makes create_file_from_pathname() reuse the verified contenthash instead
    // of attempting a second low-level file-pool write.
    ensure_filepool_path($packagepath);
    $usercontext = context_user::instance($USER->id);
    $draftid = file_get_unused_draft_itemid();
    $filerecord = [
        'component' => 'user',
        'filearea' => 'draft',
        'contextid' => $usercontext->id,
        'itemid' => $draftid,
        'filename' => basename($packagepath),
        'filepath' => '/',
    ];
    get_file_storage()->create_file_from_pathname($filerecord, $packagepath);
    return $draftid;
}

function filepool_path_for_hash(string $contenthash): string {
    global $CFG;

    return $CFG->dataroot . DIRECTORY_SEPARATOR . 'filedir' . DIRECTORY_SEPARATOR .
        substr($contenthash, 0, 2) . DIRECTORY_SEPARATOR .
        substr($contenthash, 2, 2) . DIRECTORY_SEPARATOR .
        $contenthash;
}

function filepool_payload_is_valid(string $path, string $contenthash, int $filesize): bool {
    clearstatcache(true, $path);
    return file_exists($path) && is_file($path) && @filesize($path) === $filesize && @sha1_file($path) === $contenthash;
}

function filepool_retry(callable $operation, int $attempts = 24): bool {
    for ($attempt = 0; $attempt < $attempts; $attempt++) {
        if ($operation()) {
            return true;
        }
        // Windows antivirus/indexing can hold a newly-created file for several
        // seconds. Cap each pause so a persistent failure still returns in a
        // bounded amount of time while transient locks get a fair retry window.
        usleep(min(1000000, 125000 * ($attempt + 1)));
    }
    return false;
}

function filepool_staging_directory(): string {
    global $CFG;

    $directory = $CFG->tempdir . DIRECTORY_SEPARATOR . 'flw_filepool_seed';
    check_dir_exists($directory, true, true);
    return $directory;
}

function filepool_temp_candidates(string $final): array {
    $candidates = [$final . '.tmp'];
    $seedcandidates = glob($final . '.codexseed.*') ?: [];
    return array_values(array_unique(array_merge($candidates, $seedcandidates)));
}

function cleanup_redundant_filepool_temps(string $final, string $contenthash, int $filesize): void {
    if (!filepool_payload_is_valid($final, $contenthash, $filesize)) {
        return;
    }
    foreach (filepool_temp_candidates($final) as $candidate) {
        if (filepool_payload_is_valid($candidate, $contenthash, $filesize)) {
            filepool_retry(fn() => !file_exists($candidate) || @unlink($candidate), 4);
        }
    }
}

function recover_orphaned_filepool_temp(string $final, string $contenthash, int $filesize): bool {
    foreach (filepool_temp_candidates($final) as $candidate) {
        clearstatcache(true, $candidate);
        if (!filepool_payload_is_valid($candidate, $contenthash, $filesize)) {
            continue;
        }
        // Do not race another PHP process that has only just finished writing.
        if ((time() - (int)filemtime($candidate)) < 5) {
            continue;
        }
        $promoted = filepool_retry(function() use ($candidate, $final, $contenthash, $filesize) {
            if (filepool_payload_is_valid($final, $contenthash, $filesize)) {
                return true;
            }
            return @rename($candidate, $final) || @copy($candidate, $final);
        });
        if ($promoted && filepool_payload_is_valid($final, $contenthash, $filesize)) {
            if (file_exists($candidate)) {
                filepool_retry(fn() => !file_exists($candidate) || @unlink($candidate), 4);
            }
            return true;
        }
    }
    return false;
}

function ensure_filepool_hash_from_payload(string $contenthash, int $filesize, callable $writer): string {
    global $CFG;

    if (!preg_match('/^[a-f0-9]{40}$/', $contenthash)) {
        throw new file_exception('storedfileproblem', 'Invalid content hash while seeding file pool');
    }
    $final = filepool_path_for_hash($contenthash);
    if (file_exists($final)) {
        if (filepool_payload_is_valid($final, $contenthash, $filesize)) {
            cleanup_redundant_filepool_temps($final, $contenthash, $filesize);
            return 'existing';
        }
        throw new file_exception('storedfileproblem', 'Existing file-pool content is invalid for ' . $contenthash);
    }

    $dir = dirname($final);
    if (!is_dir($dir)) {
        $dirpermissions = isset($CFG->directorypermissions) ? $CFG->directorypermissions : 0777;
        if (!mkdir($dir, $dirpermissions, true) && !is_dir($dir)) {
            throw new file_exception('storedfilecannotcreatefiledirs');
        }
    }
    if (recover_orphaned_filepool_temp($final, $contenthash, $filesize)) {
        return 'existing';
    }

    // Do not materialize the staging payload beside the final file. On Windows,
    // Defender/indexing may lock a newly-created *.codexseed file in filedir
    // long enough for Moodle's normal atomic rename to fail. Moodle temp is on
    // the same dataroot volume, so promotion into filedir remains atomic while
    // avoiding that file-pool watcher race.
    $tmp = filepool_staging_directory() . DIRECTORY_SEPARATOR . $contenthash .
        '.codexseed.' . getmypid() . '.' . str_replace('.', '', uniqid('', true));
    // Large media is first expanded into Moodle temp. Windows may scan and lock
    // that source before this copy starts, so retry the write operation itself;
    // checksum retries alone cannot recover when no complete staging file was
    // produced.
    $written = filepool_retry(fn() => $writer($tmp) !== false);
    if (!$written) {
        @unlink($tmp);
        throw new file_exception('storedfilecannotcreatefile');
    }
    // The writer may have completed while an antivirus/indexer still holds a
    // read lock. Retry the checksum instead of treating that transient lock as
    // corrupt content and immediately discarding a valid staging payload.
    if (!filepool_retry(fn() => filepool_payload_is_valid($tmp, $contenthash, $filesize))) {
        @unlink($tmp);
        throw new file_exception('storedfilecannotcreatefile');
    }

    if (filepool_payload_is_valid($final, $contenthash, $filesize)) {
        filepool_retry(fn() => !file_exists($tmp) || @unlink($tmp), 4);
        return 'existing';
    }

    $promoted = filepool_retry(function() use ($tmp, $final, $contenthash, $filesize) {
        clearstatcache(true, $tmp);
        clearstatcache(true, $final);
        if (filepool_payload_is_valid($final, $contenthash, $filesize)) {
            return true;
        }
        return @rename($tmp, $final) || @copy($tmp, $final);
    });
    $finalvalid = $promoted && filepool_retry(
        fn() => filepool_payload_is_valid($final, $contenthash, $filesize)
    );
    if (!$finalvalid) {
        filepool_retry(fn() => !file_exists($tmp) || @unlink($tmp), 4);
        throw new file_exception('storedfilecannotcreatefile');
    }
    if (file_exists($tmp)) {
        filepool_retry(fn() => !file_exists($tmp) || @unlink($tmp), 4);
    }
    $filepermissions = isset($CFG->filepermissions) ? $CFG->filepermissions : 0666;
    @chmod($final, $filepermissions);
    return 'seeded';
}

function ensure_filepool_string(string $content): string {
    $contenthash = sha1($content);
    $filesize = strlen($content);
    return ensure_filepool_hash_from_payload($contenthash, $filesize, function(string $tmp) use ($content) {
        return file_put_contents($tmp, $content, LOCK_EX);
    });
}

function ensure_filepool_path(string $sourcepath): string {
    $contenthash = sha1_file($sourcepath);
    $filesize = filesize($sourcepath);
    return ensure_filepool_hash_from_payload($contenthash, $filesize, function(string $tmp) use ($sourcepath) {
        return copy($sourcepath, $tmp);
    });
}

function seed_filepool_entry(callable $operation, string $pathname): string {
    try {
        return $operation();
    } catch (Throwable $e) {
        throw new RuntimeException(
            'FILEPOOL_SEED_ENTRY_FAILED [' . $pathname . ']: ' . $e->getMessage(),
            0,
            $e
        );
    }
}

function seed_zip_contents_in_filepool(string $packagepath): array {
    global $CFG;

    check_dir_exists($CFG->tempdir . '/zip');
    $ziparch = new zip_archive();
    if (!$ziparch->open($packagepath, file_archive::OPEN)) {
        throw new file_exception('storedfileproblem', 'Cannot open SCORM zip for file-pool seeding: ' . $packagepath);
    }

    $stats = [
        'files' => 0,
        'seeded' => 0,
        'existing' => 0,
        'bytes' => 0,
    ];
    foreach ($ziparch as $info) {
        if ($info->pathname === '' || $info->is_directory) {
            continue;
        }
        $stats['files']++;
        $stats['bytes'] += (int)$info->size;

        if ($info->size < 2097151) {
            $stream = $ziparch->get_stream($info->index);
            if (!$stream) {
                $ziparch->close();
                throw new file_exception('storedfileproblem', 'Cannot read zip entry: ' . $info->pathname);
            }
            $content = stream_get_contents($stream);
            fclose($stream);
            if ($content === false || strlen($content) !== (int)$info->size) {
                $ziparch->close();
                throw new file_exception('storedfileproblem', 'Cannot fully read zip entry: ' . $info->pathname);
            }
            $status = seed_filepool_entry(
                fn() => ensure_filepool_string($content),
                $info->pathname
            );
        } else {
            $tmp = tempnam($CFG->tempdir . '/zip', 'codexseed');
            $out = fopen($tmp, 'wb');
            $stream = $ziparch->get_stream($info->index);
            if (!$out || !$stream) {
                if ($stream) {
                    fclose($stream);
                }
                if ($out) {
                    fclose($out);
                }
                @unlink($tmp);
                $ziparch->close();
                throw new file_exception('storedfileproblem', 'Cannot read large zip entry: ' . $info->pathname);
            }
            while (!feof($stream)) {
                fwrite($out, fread($stream, 262143));
            }
            fclose($stream);
            fclose($out);
            if (filesize($tmp) !== (int)$info->size) {
                @unlink($tmp);
                $ziparch->close();
                throw new file_exception('storedfileproblem', 'Cannot fully read large zip entry: ' . $info->pathname);
            }
            $status = seed_filepool_entry(
                fn() => ensure_filepool_path($tmp),
                $info->pathname
            );
            @unlink($tmp);
        }

        if ($status === 'seeded') {
            $stats['seeded']++;
        } else {
            $stats['existing']++;
        }
    }
    $ziparch->close();
    return $stats;
}

function find_or_create_pilot_section(stdClass $course, string $sectionname, bool $dryrun): int {
    global $DB;

    $records = $DB->get_records('course_sections', ['course' => $course->id], 'section ASC');
    foreach ($records as $section) {
        if (trim((string)$section->name) === $sectionname) {
            return (int)$section->section;
        }
    }

    $nextsection = 0;
    foreach ($records as $section) {
        $nextsection = max($nextsection, (int)$section->section + 1);
    }
    if ($nextsection < 1) {
        $nextsection = 1;
    }
    if ($dryrun) {
        return $nextsection;
    }

    course_create_sections_if_missing($course, $nextsection);
    rebuild_course_cache($course->id, true);
    $section = $DB->get_record('course_sections', ['course' => $course->id, 'section' => $nextsection], '*', MUST_EXIST);
    course_update_section($course, $section, [
        'name' => $sectionname,
        'summary' => '<p>SCORM pilot imports generated by the Smart Course editor.</p>',
        'summaryformat' => FORMAT_HTML,
        'visible' => 1,
    ]);
    rebuild_course_cache($course->id, true);
    return $nextsection;
}

function build_scorm_moduleinfo(stdClass $course, int $sectionnum, array $item, string $stamp, string $nameprefix = 'SCORM Pilot'): stdClass {
    $cfgscorm = get_config('scorm');
    [, , , , $data] = prepare_new_moduleinfo_data($course, 'scorm', $sectionnum);
    $packagepath = $item['export']['zipPath'];
    $title = clean_short_text($item['title'] ?? ($item['label'] ?? basename($packagepath)), 1333);
    $idnumber = make_idnumber($item, $stamp);

    $safeNamePrefix = clean_short_text($nameprefix ?: 'SCORM Pilot', 80);
    $data->name = '[' . $safeNamePrefix . ' ' . $stamp . '] ' . $title;
    $data->cmidnumber = $idnumber;
    $data->introeditor = [
        'text' => '<p>Imported by Smart Course editor pilot from ' . s($item['root'] ?? '') . '.</p>',
        'format' => FORMAT_HTML,
        'itemid' => file_get_unused_draft_itemid(),
    ];
    $data->scormtype = SCORM_TYPE_LOCAL;
    $data->packagefile = draft_file_from_path($packagepath);
    $data->packageurl = '';
    $data->reference = basename($packagepath);
    $data->version = '';
    $data->maxgrade = cfg_value($cfgscorm, 'maxgrade', 100);
    $data->grademethod = cfg_value($cfgscorm, 'grademethod', GRADESCOES);
    $data->whatgrade = cfg_value($cfgscorm, 'whatgrade', HIGHESTATTEMPT);
    $data->maxattempt = cfg_value($cfgscorm, 'maxattempt', 1);
    $data->forcecompleted = cfg_value($cfgscorm, 'forcecompleted', 0);
    $data->forcenewattempt = cfg_value($cfgscorm, 'forcenewattempt', SCORM_FORCEATTEMPT_NO);
    $data->lastattemptlock = cfg_value($cfgscorm, 'lastattemptlock', 0);
    $data->masteryoverride = cfg_value($cfgscorm, 'masteryoverride', 1);
    // S2B: the FLW in-unit navigator is the learner-facing lesson/component navigator.
    // Keep Moodle's SCORM player responsible for launching/tracking the active scoid,
    // but do not expose Moodle's native package structure as a competing lesson list.
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
    $data->navpositionleft = cfg_value($cfgscorm, 'navpositionleft', -100);
    $data->navpositiontop = cfg_value($cfgscorm, 'navpositiontop', -100);
    $data->auto = cfg_value($cfgscorm, 'auto', 0);
    $data->popup = 0;
    $data->options = '';
    $data->width = cfg_value($cfgscorm, 'framewidth', 100);
    $data->height = cfg_value($cfgscorm, 'frameheight', 600);
    $data->timeopen = 0;
    $data->timeclose = 0;
    $data->timemodified = time();
    $data->completionstatusrequired = null;
    $data->completionscorerequired = null;
    $data->completionstatusallscos = 0;
    $data->autocommit = cfg_value($cfgscorm, 'autocommit', 0);
    $data->tags = [];
    return $data;
}

function import_item(stdClass $course, int $sectionnum, array $item, string $stamp, bool $dryrun, string $nameprefix = 'SCORM Pilot'): array {
    global $DB, $CFG;

    if (($item['status'] ?? '') !== 'exported') {
        return [
            'label' => $item['label'] ?? '',
            'unit' => $item['unit'] ?? '',
            'status' => 'skipped',
            'reason' => 'Package was not exported successfully.',
        ];
    }
    $packagepath = $item['export']['zipPath'] ?? '';
    if (!file_exists($packagepath)) {
        throw new moodle_exception('filenotfound', 'error', '', $packagepath);
    }

    $idnumber = make_idnumber($item, $stamp);
    $existing = $DB->get_record('course_modules', ['course' => $course->id, 'idnumber' => $idnumber], '*', IGNORE_MISSING);
    if ($existing) {
        $scorm = null;
        if ((int)$existing->instance > 0) {
            $scorm = $DB->get_record('scorm', ['id' => $existing->instance], '*', IGNORE_MISSING);
        }
        return [
            'label' => $item['label'] ?? '',
            'unit' => $item['unit'] ?? '',
            'status' => 'already_exists',
            'cmid' => (int)$existing->id,
            'scormId' => $scorm ? (int)$scorm->id : null,
            'viewUrl' => $CFG->wwwroot . '/mod/scorm/view.php?id=' . $existing->id,
        ];
    }

    if ($dryrun) {
        return [
            'label' => $item['label'] ?? '',
            'unit' => $item['unit'] ?? '',
            'status' => 'dry_run_ready',
            'idnumber' => $idnumber,
            'packagePath' => $packagepath,
            'manifestScoCount' => $item['export']['scoCount'] ?? null,
        ];
    }

    $seedstats = seed_zip_contents_in_filepool($packagepath);
    $moduleinfo = build_scorm_moduleinfo($course, $sectionnum, $item, $stamp, $nameprefix);
    try {
        $created = add_moduleinfo($moduleinfo, $course);
    } catch (Throwable $e) {
        if ($DB->is_transaction_started()) {
            $DB->force_transaction_rollback();
        }
        throw $e;
    }
    rebuild_course_cache($course->id, true);

    $cmid = (int)$created->coursemodule;
    $scormid = (int)$created->instance;
    $scorm = $DB->get_record('scorm', ['id' => $scormid], '*', MUST_EXIST);
    $allscoes = $DB->get_records('scorm_scoes', ['scorm' => $scormid], 'sortorder ASC, id ASC');
    $launchscoes = array_values(array_filter($allscoes, function($sco) {
        return isset($sco->scormtype) && $sco->scormtype === 'sco';
    }));

    return [
        'label' => $item['label'] ?? '',
        'unit' => $item['unit'] ?? '',
        'status' => 'imported',
        'cmid' => $cmid,
        'scormId' => $scormid,
        'name' => $created->name,
        'idnumber' => $created->cmidnumber,
        'reference' => $scorm->reference,
        'manifestScoCount' => $item['export']['scoCount'] ?? null,
        'moodleScoRows' => count($allscoes),
        'moodleLaunchScoRows' => count($launchscoes),
        'filePoolSeed' => $seedstats,
        'viewUrl' => $CFG->wwwroot . '/mod/scorm/view.php?id=' . $cmid,
    ];
}

function normalize_import_mode($value): string {
    $mode = strtolower(trim((string)($value ?? 'overwrite')));
    $mode = str_replace(['-', ' '], '_', $mode);
    $aliases = [
        'addnew' => 'add_new',
        'add' => 'add_new',
        'new' => 'add_new',
        'clearandadd' => 'clear_add',
        'clear_and_add' => 'clear_add',
        'clear_add_new' => 'clear_add',
        'rebuild' => 'clear_add',
        'rebuild_selected_flw_scope' => 'clear_add',
        'rebuild_selected_units' => 'clear_add',
    ];
    $mode = $aliases[$mode] ?? $mode;
    return in_array($mode, ['overwrite', 'add_new', 'clear_add'], true) ? $mode : 'overwrite';
}

function item_unit_number(array $item): int {
    $raw = (string)($item['unit'] ?? '001');
    if (preg_match('/(\d{1,3})/', $raw, $matches)) {
        return max(1, (int)$matches[1]);
    }
    return 1;
}

function unit_search_terms(int $unit): array {
    $plain = (string)$unit;
    $padded = sprintf('%03d', $unit);
    return [
        'unit ' . $plain,
        'unit' . $plain,
        'unit ' . $padded,
        'unit' . $padded,
        'u' . $padded,
        'u' . $plain,
    ];
}

function s3_clean_key($value): string {
    return trim((string)($value ?? ''));
}

function s3_upper_key($value): string {
    return strtoupper(s3_clean_key($value));
}

function s3_target_metadata(array $item): array {
    $target = $item['targetMetadata'] ?? [];
    if (!is_array($target)) {
        $target = [];
    }
    $merged = $target;
    foreach ([
        'sourceRootCode',
        'worldCode',
        'worldTitle',
        'languageCode',
        'sourceStage',
        'deploymentStageCode',
        'unitId',
        'unitNumber',
        'unitSequence',
        'unitTitle',
        'courseExternalKey',
        'courseShortname',
        'courseIdnumber',
        'unitExternalKey',
        'scormActivityExternalKey',
        'futureCmidNumber',
        'scormManifestIdentifier',
        'packageSha256',
        'packageContentSha256',
        'componentMappings',
        'microActivityMappings',
        'courseImage',
        'scoIdentifierRule',
        'preflightStatus',
        'stageResolutionStatus',
        'stageResolutionMessage',
        'moodleCategory',
    ] as $field) {
        if (!array_key_exists($field, $merged) && array_key_exists($field, $item)) {
            $merged[$field] = $item[$field];
        }
    }
    return $merged;
}

function s3_stage_course_fullname(array $target): string {
    $worldtitle = s3_clean_key($target['worldTitle'] ?? '');
    $stage = s3_clean_key($target['deploymentStageCode'] ?? '');
    if ($worldtitle !== '' && $stage !== '') {
        return clean_short_text($worldtitle . ' — ' . $stage, 254);
    }
    return clean_short_text('FLW Stage Course ' . s3_clean_key($target['courseExternalKey'] ?? ''), 254);
}

function stage_course_definition(array $item): array {
    $target = s3_target_metadata($item);
    $worldcode = s3_upper_key($target['worldCode'] ?? '');
    $stage = s3_clean_key($target['deploymentStageCode'] ?? '');
    $preflight = s3_clean_key($target['preflightStatus'] ?? $target['stageResolutionStatus'] ?? '');
    $coursekey = s3_clean_key($target['courseExternalKey'] ?? $target['courseIdnumber'] ?? '');
    $shortname = s3_clean_key($target['courseShortname'] ?? '');
    $category = $target['moodleCategory'] ?? null;
    $unitnumber = s3_clean_key($target['unitNumber'] ?? $item['unit'] ?? '');
    $unitid = s3_clean_key($target['unitId'] ?? ($worldcode && $unitnumber ? $worldcode . '-U' . sprintf('%03d', item_unit_number($item)) : ''));

    if ($stage === '' || $preflight === 'STAGE_UNRESOLVED') {
        return [
            'valid' => false,
            'status' => 'STAGE_UNRESOLVED',
            'message' => s3_clean_key($target['stageResolutionMessage'] ?? 'Deployment stage is unresolved.'),
            'target' => $target,
            'item' => $item,
        ];
    }
    if ($preflight === 'STAGE_CONFLICT') {
        return [
            'valid' => false,
            'status' => 'STAGE_CONFLICT',
            'message' => s3_clean_key($target['stageResolutionMessage'] ?? 'Deployment stage is conflicting.'),
            'target' => $target,
            'item' => $item,
        ];
    }
    if ($worldcode === '' || $coursekey === '') {
        return [
            'valid' => false,
            'status' => $preflight ?: 'STAGE_UNRESOLVED',
            'message' => s3_clean_key($target['stageResolutionMessage'] ?? 'World/stage course identity is incomplete.'),
            'target' => $target,
            'item' => $item,
        ];
    }

    if ($shortname === '') {
        $shortname = 'FLW-' . $worldcode . '-' . preg_replace('/[^A-Za-z0-9]+/', '-', strtoupper($stage));
    }

    return [
        'valid' => true,
        'status' => 'RESOLVED',
        'sourceRootCode' => s3_clean_key($target['sourceRootCode'] ?? $item['code'] ?? ''),
        'worldCode' => $worldcode,
        'worldTitle' => s3_clean_key($target['worldTitle'] ?? ''),
        'languageCode' => s3_clean_key($target['languageCode'] ?? ''),
        'sourceStage' => s3_clean_key($target['sourceStage'] ?? ''),
        'deploymentStageCode' => $stage,
        'courseExternalKey' => $coursekey,
        'courseIdnumber' => $coursekey,
        'courseShortname' => clean_short_text($shortname, 100),
        'courseFullname' => s3_stage_course_fullname($target),
        'moodleCategory' => is_numeric($category) ? (int)$category : 0,
        'unitId' => $unitid,
        'unitNumber' => $unitnumber,
        'unitSequence' => (int)($target['unitSequence'] ?? item_unit_number($item)),
        'unitTitle' => s3_clean_key($target['unitTitle'] ?? $item['title'] ?? ''),
        'target' => $target,
        'item' => $item,
    ];
}

function stage_group_key(array $definition): string {
    if (empty($definition['valid'])) {
        return 'INVALID:' . ($definition['status'] ?? 'UNKNOWN') . ':' . spl_object_id((object)$definition);
    }
    return $definition['worldCode'] . ':' . $definition['deploymentStageCode'];
}

function stage_course_groups(array $items, array $allowedstatuses): array {
    $groups = [];
    foreach ($items as $item) {
        $status = (string)($item['status'] ?? '');
        if (!in_array($status, $allowedstatuses, true)) {
            $groups[] = [
                'key' => 'SOURCE:' . md5(json_encode($item)),
                'definition' => [
                    'valid' => false,
                    'status' => $status === 'missing' ? 'missing_source_unit' : 'skipped',
                    'message' => $item['reason'] ?? 'Package was not exported successfully.',
                    'item' => $item,
                ],
                'items' => [$item],
            ];
            continue;
        }
        $definition = stage_course_definition($item);
        $key = stage_group_key($definition);
        if (!isset($groups[$key])) {
            $groups[$key] = [
                'key' => $key,
                'definition' => $definition,
                'items' => [],
            ];
        }
        $groups[$key]['items'][] = $item;
    }
    return array_values($groups);
}

function course_image_extension(string $path): string {
    $extension = strtolower((string)pathinfo($path, PATHINFO_EXTENSION));
    return in_array($extension, ['png', 'jpg', 'jpeg', 'gif', 'webp'], true) ? $extension : '';
}

function normalize_course_image_member(string $value, string $base = ''): string {
    $value = html_entity_decode(trim($value), ENT_QUOTES | ENT_HTML5, 'UTF-8');
    if ($value === '' || strpos($value, "\0") !== false || preg_match('/^[A-Za-z][A-Za-z0-9+.-]*:/', $value)) {
        return '';
    }
    $value = str_replace('\\', '/', rawurldecode(preg_split('/[?#]/', $value, 2)[0] ?? ''));
    if ($value === '' || str_starts_with($value, '/')) {
        return '';
    }
    $combined = trim($base, '/');
    $combined = ($combined !== '' ? $combined . '/' : '') . $value;
    $parts = [];
    foreach (explode('/', $combined) as $part) {
        if ($part === '' || $part === '.') {
            continue;
        }
        if ($part === '..') {
            if (!$parts) {
                return '';
            }
            array_pop($parts);
            continue;
        }
        $parts[] = $part;
    }
    $normalized = implode('/', $parts);
    return course_image_extension($normalized) !== '' ? $normalized : '';
}

function item_package_path(array $item): string {
    $export = is_array($item['export'] ?? null) ? $item['export'] : [];
    $batchtarget = is_array($item['batchTarget'] ?? null) ? $item['batchTarget'] : [];
    return trim((string)($export['zipPath'] ?? $item['packagePath'] ?? $batchtarget['packagePath'] ?? ''));
}

function item_course_image_metadata(array $item): array {
    $export = is_array($item['export'] ?? null) ? $item['export'] : [];
    $batchtarget = is_array($item['batchTarget'] ?? null) ? $item['batchTarget'] : [];
    $metadata = $export['courseImage'] ?? $item['courseImage'] ?? $batchtarget['courseImage'] ?? [];
    return is_array($metadata) ? $metadata : [];
}

function zip_course_image_member(ZipArchive $zip, string $member): string {
    $member = normalize_course_image_member($member);
    if ($member === '') {
        return '';
    }
    $index = $zip->locateName($member);
    if ($index === false && defined('ZipArchive::FL_NOCASE')) {
        $index = $zip->locateName($member, ZipArchive::FL_NOCASE);
    }
    return $index === false ? '' : (string)$zip->getNameIndex($index);
}

function first_html_course_image_member(ZipArchive $zip): string {
    $indexmember = $zip_course_image_member($zip, 'index.html');
    if ($indexmember === '') {
        return '';
    }
    $html = $zip->getFromName($indexmember);
    if (!is_string($html) || $html === '') {
        return '';
    }
    if (preg_match_all('/<img\b[^>]*>/is', $html, $tags)) {
        foreach ($tags[0] as $tag) {
            if (!preg_match("/\\bsrc\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))/is", $tag, $match)) {
                continue;
            }
            $reference = $match[1] ?? $match[2] ?? $match[3] ?? '';
            if (strpos($reference, '${') !== false) {
                continue;
            }
            $member = normalize_course_image_member($reference, dirname($indexmember) === '.' ? '' : dirname($indexmember));
            $found = zip_course_image_member($zip, $member);
            if ($found !== '') {
                return $found;
            }
        }
    }
    return '';
}

function fallback_course_image_member(ZipArchive $zip): string {
    $members = [];
    for ($index = 0; $index < $zip->numFiles; $index++) {
        $name = (string)$zip->getNameIndex($index);
        $normalized = normalize_course_image_member($name);
        if ($normalized === '' || str_starts_with(strtolower($normalized), 'scos/') || str_starts_with(strtolower($normalized), 'assets/scorm/')) {
            continue;
        }
        $members[] = $name;
    }
    natcasesort($members);
    return $members ? (string)reset($members) : '';
}

function unit_package_course_image_candidate(array $item): array {
    $packagepath = item_package_path($item);
    if ($packagepath === '' || !is_file($packagepath)) {
        return [
            'status' => ($item['status'] ?? '') === 'planned' ? 'COURSE_IMAGE_PENDING_EXPORT' : 'COURSE_IMAGE_PACKAGE_MISSING',
            'message' => 'A SCORM package is required before its Unit image can be resolved.',
        ];
    }

    $zip = new ZipArchive();
    if ($zip->open($packagepath) !== true) {
        return ['status' => 'COURSE_IMAGE_PACKAGE_INVALID', 'message' => 'Could not open SCORM ZIP while resolving its course image.', 'packagePath' => $packagepath];
    }
    try {
        $metadata = item_course_image_metadata($item);
        $member = zip_course_image_member($zip, (string)($metadata['packagePath'] ?? ''));
        $selectionsource = (string)($metadata['selectionSource'] ?? 'export_metadata');
        if ($member === '') {
            $member = first_html_course_image_member($zip);
            $selectionsource = 'package_index_html';
        }
        if ($member === '') {
            $member = fallback_course_image_member($zip);
            $selectionsource = 'package_sorted_asset_fallback';
        }
        if ($member === '') {
            return ['status' => 'NO_UNIT_IMAGE', 'message' => 'No usable raster image was found in this Unit SCORM package.', 'packagePath' => $packagepath];
        }
        $target = s3_target_metadata($item);
        return [
            'status' => 'COURSE_IMAGE_RESOLVED',
            'packagePath' => $packagepath,
            'packageMember' => $member,
            'sourceFilename' => basename($member),
            'selectionSource' => $selectionsource,
            'unitId' => (string)($target['unitId'] ?? $item['unitId'] ?? ''),
            'unitNumber' => sprintf('%03d', item_unit_number($item)),
            'sourceSha256' => (string)($metadata['sha256'] ?? ''),
        ];
    } finally {
        $zip->close();
    }
}

function stage_group_course_image_candidate(array $group): array {
    $items = array_values($group['items'] ?? []);
    usort($items, function(array $left, array $right): int {
        $unitcompare = item_unit_number($left) <=> item_unit_number($right);
        if ($unitcompare !== 0) {
            return $unitcompare;
        }
        $lefttarget = s3_target_metadata($left);
        $righttarget = s3_target_metadata($right);
        return strcmp((string)($lefttarget['unitId'] ?? ''), (string)($righttarget['unitId'] ?? ''));
    });
    $pending = false;
    $errors = [];
    foreach ($items as $item) {
        $candidate = unit_package_course_image_candidate($item);
        if (($candidate['status'] ?? '') === 'COURSE_IMAGE_RESOLVED') {
            return $candidate;
        }
        if (($candidate['status'] ?? '') === 'COURSE_IMAGE_PENDING_EXPORT') {
            $pending = true;
        } elseif (!in_array(($candidate['status'] ?? ''), ['NO_UNIT_IMAGE'], true)) {
            $errors[] = $candidate;
        }
    }
    if ($errors) {
        $first = reset($errors);
        return [
            'status' => $first['status'] ?? 'COURSE_IMAGE_SELECTION_FAILED',
            'message' => $first['message'] ?? 'Could not resolve a Unit image from the exported SCORM package.',
            'details' => $errors,
        ];
    }
    if ($pending) {
        return ['status' => 'COURSE_IMAGE_PENDING_EXPORT', 'message' => 'Course image will be resolved after the selected Unit packages are exported.'];
    }
    return ['status' => 'NO_UNIT_IMAGE', 'message' => 'No usable raster image was found in the selected Unit packages.'];
}

function extract_course_image_candidate(array $candidate): array {
    global $CFG;

    $packagepath = (string)($candidate['packagePath'] ?? '');
    $member = (string)($candidate['packageMember'] ?? '');
    $zip = new ZipArchive();
    if ($packagepath === '' || $member === '' || $zip->open($packagepath) !== true) {
        throw new RuntimeException('Could not open the Unit SCORM ZIP while extracting its course image.');
    }
    $temp = '';
    try {
        $actualmember = zip_course_image_member($zip, $member);
        if ($actualmember === '') {
            throw new RuntimeException('The selected Unit image is no longer present in the SCORM ZIP.');
        }
        $stat = $zip->statName($actualmember);
        $size = is_array($stat) ? (int)($stat['size'] ?? 0) : 0;
        $extension = course_image_extension($actualmember);
        if ($extension === '') {
            throw new RuntimeException('The selected course image has an unsupported file extension.');
        }
        $directory = make_temp_directory('flw_course_images');
        $tempbase = tempnam($directory, 'flwimg_');
        if ($tempbase === false) {
            throw new RuntimeException('Could not allocate a Moodle temporary file for the course image.');
        }
        // Keep Moodle's atomically-created temporary pathname. On Windows,
        // antivirus/indexing can briefly hold the new file and make an
        // immediate rename fail even though the file is fully writable.
        // Image validation uses the file signature, and the final Moodle
        // overview filename receives the source extension separately.
        $temp = $tempbase;
        $input = $zip->getStream($actualmember);
        $output = fopen($temp, 'wb');
        if (!$input || !$output) {
            if ($input) {
                fclose($input);
            }
            if ($output) {
                fclose($output);
            }
            throw new RuntimeException('Could not read the selected Unit image from the SCORM ZIP.');
        }
        $written = stream_copy_to_stream($input, $output);
        fclose($input);
        fclose($output);
        if ($written === false || ($size > 0 && $written !== $size)) {
            throw new RuntimeException('The selected Unit image was not fully extracted from the SCORM ZIP.');
        }
        $imageinfo = @getimagesize($temp);
        if ($imageinfo === false) {
            throw new RuntimeException('The first Unit image is not a valid raster image.');
        }
        return [
            'tempPath' => $temp,
            'size' => (int)filesize($temp),
            'sha1' => (string)sha1_file($temp),
            'mimeType' => (string)($imageinfo['mime'] ?? 'application/octet-stream'),
            'width' => (int)($imageinfo[0] ?? 0),
            'height' => (int)($imageinfo[1] ?? 0),
            'extension' => $extension,
            'packageMember' => $actualmember,
        ];
    } catch (Throwable $e) {
        if ($temp !== '' && file_exists($temp)) {
            @unlink($temp);
        }
        throw $e;
    } finally {
        $zip->close();
    }
}

function course_image_failure_status(string $status): bool {
    return in_array($status, [
        'COURSE_IMAGE_PACKAGE_MISSING',
        'COURSE_IMAGE_PACKAGE_INVALID',
        'COURSE_IMAGE_CONFIG_DISABLED',
        'COURSE_IMAGE_TYPE_REJECTED',
        'COURSE_IMAGE_TOO_LARGE',
        'COURSE_IMAGE_PERMISSION_DENIED',
        'COURSE_IMAGE_UPDATE_FAILED',
        'COURSE_IMAGE_SELECTION_FAILED',
    ], true);
}

function sync_stage_course_image(array $group, array $resolution, bool $dryrun): array {
    global $DB;

    $candidate = stage_group_course_image_candidate($group);
    $status = (string)($candidate['status'] ?? 'NO_UNIT_IMAGE');
    if ($status !== 'COURSE_IMAGE_RESOLVED') {
        return $candidate;
    }

    $options = course_overviewfiles_options((object)[]);
    if (!$options) {
        return array_merge($candidate, [
            'status' => 'COURSE_IMAGE_CONFIG_DISABLED',
            'message' => 'Moodle course overview images are disabled by site configuration.',
        ]);
    }
    $coursearray = is_array($resolution['course'] ?? null) ? $resolution['course'] : [];
    $courseid = (int)($coursearray['courseId'] ?? 0);
    if ($courseid <= 0) {
        if ($dryrun && ($resolution['status'] ?? '') === 'CREATE_STAGE_COURSE') {
            return array_merge($candidate, [
                'status' => 'WOULD_SET_COURSE_IMAGE_ON_CREATE',
                'action' => 'SET_ON_CREATE',
                'message' => 'The new World/Stage course would use the first usable image from the lowest-numbered selected Unit.',
            ]);
        }
        return array_merge($candidate, [
            'status' => 'COURSE_IMAGE_COURSE_NOT_RESOLVED',
            'message' => 'The Stage Course must be resolved before its course image can be set.',
        ]);
    }

    $course = $DB->get_record('course', ['id' => $courseid], '*', IGNORE_MISSING);
    if (!$course) {
        return array_merge($candidate, ['status' => 'COURSE_IMAGE_COURSE_NOT_RESOLVED', 'message' => 'The resolved Moodle course no longer exists.']);
    }
    $context = context_course::instance($courseid);
    $options = course_overviewfiles_options($course);
    if (!$options) {
        return array_merge($candidate, ['status' => 'COURSE_IMAGE_CONFIG_DISABLED', 'message' => 'Moodle course overview images are disabled by site configuration.']);
    }

    $extracted = null;
    try {
        $extracted = extract_course_image_candidate($candidate);
        $publicextracted = $extracted;
        unset($publicextracted['tempPath']);
        $maxbytes = (int)($options['maxbytes'] ?? 0);
        if ($maxbytes > 0 && (int)$extracted['size'] > $maxbytes) {
            return array_merge($candidate, $publicextracted, [
                'status' => 'COURSE_IMAGE_TOO_LARGE',
                'message' => 'The selected Unit image exceeds Moodle\'s configured course-image size limit.',
            ]);
        }
        $definition = $resolution['definition'] ?? [];
        $identity = strtolower((string)($definition['worldCode'] ?? 'flw')) . '-' .
            strtolower((string)($definition['deploymentStageCode'] ?? 'stage')) . '-' .
            strtolower((string)($candidate['unitId'] ?? ('u' . ($candidate['unitNumber'] ?? '000'))));
        $filename = preg_replace('/[^a-z0-9_-]+/', '-', $identity) . '.' . $extracted['extension'];
        $acceptedtypes = $options['accepted_types'] ?? '*';
        $filetypes = new \core_form\filetypes_util();
        if ($acceptedtypes !== '*' && !$filetypes->is_allowed_file_type($filename, $acceptedtypes)) {
            return array_merge($candidate, $publicextracted, [
                'status' => 'COURSE_IMAGE_TYPE_REJECTED',
                'filename' => $filename,
                'message' => 'Moodle does not accept this image type for course overview images.',
            ]);
        }

        $fs = get_file_storage();
        $existing = array_values($fs->get_area_files($context->id, 'course', 'overviewfiles', 0, 'id ASC', false));
        $currentfiles = array_map(fn($file) => [
            'filename' => $file->get_filename(),
            'contentHash' => $file->get_contenthash(),
            'size' => $file->get_filesize(),
        ], $existing);
        if (count($existing) === 1 && $existing[0]->get_contenthash() === $extracted['sha1']) {
            return array_merge($candidate, $publicextracted, [
                'status' => 'COURSE_IMAGE_UNCHANGED',
                'action' => 'UNCHANGED',
                'filename' => $existing[0]->get_filename(),
                'previousFiles' => $currentfiles,
                'message' => 'Moodle course image already matches the selected Unit image.',
            ]);
        }
        $action = $existing ? 'UPDATE_COURSE_IMAGE' : 'SET_COURSE_IMAGE';
        if ($dryrun) {
            return array_merge($candidate, $publicextracted, [
                'status' => 'WOULD_' . $action,
                'action' => $action,
                'filename' => $filename,
                'previousFiles' => $currentfiles,
                'message' => $existing ? 'Moodle course image would be replaced with the selected Unit image.' : 'Moodle course image would be set from the selected Unit image.',
            ]);
        }
        if (!has_capability('moodle/course:update', $context)) {
            return array_merge($candidate, $publicextracted, [
                'status' => 'COURSE_IMAGE_PERMISSION_DENIED',
                'message' => 'Current Moodle user cannot update the resolved course image.',
            ]);
        }

        ensure_filepool_path($extracted['tempPath']);
        $transaction = $DB->start_delegated_transaction();
        try {
            $fs->delete_area_files($context->id, 'course', 'overviewfiles', 0);
            $stored = $fs->create_file_from_pathname([
                'contextid' => $context->id,
                'component' => 'course',
                'filearea' => 'overviewfiles',
                'itemid' => 0,
                'filepath' => '/',
                'filename' => $filename,
            ], $extracted['tempPath']);
            if (!$stored || !$stored->is_valid_image()) {
                throw new RuntimeException('Moodle rejected the selected Unit image after storing it.');
            }
            $transaction->allow_commit();
        } catch (Throwable $e) {
            if ($DB->is_transaction_started()) {
                $DB->force_transaction_rollback();
            }
            throw $e;
        }
        \cache::make('core', 'course_image')->delete($courseid);
        cache_helper::purge_by_event('changesincourse');
        return array_merge($candidate, $publicextracted, [
            'status' => $action,
            'action' => $action,
            'filename' => $filename,
            'previousFiles' => $currentfiles,
            'message' => $existing ? 'Moodle course image replaced with the selected Unit image.' : 'Moodle course image set from the selected Unit image.',
        ]);
    } catch (Throwable $e) {
        return array_merge($candidate, [
            'status' => 'COURSE_IMAGE_UPDATE_FAILED',
            'message' => $e->getMessage(),
            'class' => get_class($e),
        ]);
    } finally {
        if (is_array($extracted) && !empty($extracted['tempPath']) && file_exists($extracted['tempPath'])) {
            @unlink($extracted['tempPath']);
        }
    }
}

function stage_course_map_path(?string $path = null): string {
    if ($path && trim($path) !== '') {
        return $path;
    }
    return dirname(__DIR__) . DIRECTORY_SEPARATOR . 'flw_moodle_stage_course_map.json';
}

function load_stage_course_map(string $path): array {
    if (!file_exists($path)) {
        return ['schemaVersion' => 1, 'stageCourses' => []];
    }
    $json = file_get_contents($path);
    $data = json_decode($json ?: '', true);
    if (!is_array($data)) {
        return ['schemaVersion' => 1, 'stageCourses' => []];
    }
    if (!isset($data['stageCourses']) || !is_array($data['stageCourses'])) {
        $data['stageCourses'] = [];
    }
    return $data;
}

function save_stage_course_map(string $path, array $map): void {
    $dir = dirname($path);
    if (!is_dir($dir) && !mkdir($dir, 0777, true) && !is_dir($dir)) {
        throw new RuntimeException('Cannot create stage course map directory: ' . $dir);
    }
    file_put_contents($path, json_out($map));
}

function record_stage_course_mapping(array $definition, stdClass $course, string $status, string $map_path): void {
    $map = load_stage_course_map($map_path);
    $key = $definition['courseExternalKey'];
    $existing = $map['stageCourses'][$key] ?? [];
    $now = date('c');
    $map['stageCourses'][$key] = [
        'WorldCode' => $definition['worldCode'],
        'DeploymentStageCode' => $definition['deploymentStageCode'],
        'courseExternalKey' => $definition['courseExternalKey'],
        'moodleCourseId' => (int)$course->id,
        'moodleCourseIdnumber' => (string)$course->idnumber,
        'status' => $status,
        'createdAt' => $existing['createdAt'] ?? $now,
        'updatedAt' => $now,
    ];
    save_stage_course_map($map_path, $map);
}

function stage_course_summary_row(stdClass $course): array {
    return [
        'courseId' => (int)$course->id,
        'courseFullname' => (string)$course->fullname,
        'courseShortname' => (string)$course->shortname,
        'courseIdnumber' => (string)$course->idnumber,
        'courseCategory' => (int)$course->category,
    ];
}

function validate_stage_category(array $definition): ?array {
    global $DB;

    $category = (int)($definition['moodleCategory'] ?? 0);
    if ($category <= 0) {
        return [
            'status' => 'CATEGORY_MISSING',
            'message' => 'No configured Moodle category is available for ' . ($definition['worldCode'] ?? 'world') . ':' . ($definition['deploymentStageCode'] ?? 'stage') . '.',
            'categoryId' => $category,
        ];
    }
    $record = $DB->get_record('course_categories', ['id' => $category], 'id,name,idnumber,parent,visible', IGNORE_MISSING);
    if (!$record) {
        return [
            'status' => 'CATEGORY_MISSING',
            'message' => 'Configured Moodle category does not exist: ' . $category,
            'categoryId' => $category,
        ];
    }
    return null;
}

function stage_course_matches_definition(stdClass $course, array $definition): bool {
    return (string)$course->idnumber === (string)$definition['courseIdnumber']
        && (string)$course->shortname === (string)$definition['courseShortname']
        && (string)$course->fullname === (string)$definition['courseFullname']
        && (int)$course->category === (int)$definition['moodleCategory'];
}

function stage_course_conflict(array $definition, stdClass $course, string $reason): array {
    return [
        'status' => 'COURSE_IDNUMBER_CONFLICT',
        'courseAction' => 'COURSE_IDNUMBER_CONFLICT',
        'message' => $reason,
        'definition' => $definition,
        'course' => stage_course_summary_row($course),
        'potentialConflicts' => [],
    ];
}

function find_program1_stage_course_mapping(array $definition): ?array {
    global $DB;

    $manager = $DB->get_manager();
    if (!$manager->table_exists('flwcupkp_framework')) {
        return null;
    }
    $stage = strtoupper((string)$definition['deploymentStageCode']);
    $world = strtoupper((string)$definition['worldCode']);
    $records = $DB->get_records('flwcupkp_framework', null, 'id ASC', 'id,externalid,name,courseid,coursecode,cefrrange,status');
    foreach ($records as $record) {
        if (empty($record->courseid)) {
            continue;
        }
        $coursecode = strtoupper(trim((string)$record->coursecode));
        $cefrrange = strtoupper(trim((string)$record->cefrrange));
        if (!in_array($coursecode, [$world, $world . '2'], true) || $cefrrange !== $stage) {
            continue;
        }
        $course = $DB->get_record('course', ['id' => (int)$record->courseid], '*', IGNORE_MISSING);
        if ($course) {
            return ['record' => (array)$record, 'course' => $course];
        }
    }
    return null;
}

function find_legacy_unit_courses(array $definition, array $items): array {
    global $DB;

    $category = (int)($definition['moodleCategory'] ?? 0);
    $worldterms = array_filter([
        lower_match_text((string)($definition['worldTitle'] ?? '')),
        lower_match_text((string)($definition['worldCode'] ?? '')),
        lower_match_text((string)($definition['sourceRootCode'] ?? '')),
    ]);
    if (($definition['worldCode'] ?? '') === 'REW') {
        $worldterms[] = 'real english world';
        $worldterms[] = 'rew2';
    }
    $courses = $DB->get_records('course', null, 'id ASC', 'id,shortname,fullname,idnumber,category');
    $found = [];
    foreach ($items as $item) {
        $unit = item_unit_number($item);
        $unitterms = unit_search_terms($unit);
        foreach ($courses as $course) {
            if ($category > 0 && (int)$course->category !== $category) {
                continue;
            }
            if ((string)$course->idnumber === (string)$definition['courseIdnumber']) {
                continue;
            }
            $haystack = lower_match_text((string)$course->shortname . ' ' . (string)$course->fullname);
            $worldmatch = false;
            foreach ($worldterms as $term) {
                if ($term !== '' && haystack_has_term($haystack, $term)) {
                    $worldmatch = true;
                    break;
                }
            }
            if (!$worldmatch) {
                continue;
            }
            $unitmatch = false;
            foreach ($unitterms as $term) {
                if (haystack_has_term($haystack, $term)) {
                    $unitmatch = true;
                    break;
                }
            }
            if ($unitmatch) {
                $found[(int)$course->id] = [
                    'status' => 'LEGACY_UNIT_COURSE_FOUND',
                    'unit' => sprintf('%03d', $unit),
                    'course' => stage_course_summary_row($course),
                    'message' => 'Legacy Unit Moodle Course candidate found; S3 does not adopt, delete, or migrate it.',
                ];
            }
        }
    }
    return array_values($found);
}

function stage_course_permission(array $definition): array {
    $category = (int)($definition['moodleCategory'] ?? 0);
    if ($category <= 0) {
        return ['canCreate' => false, 'capability' => 'moodle/course:create', 'context' => 'coursecat:' . $category];
    }
    $context = context_coursecat::instance($category);
    return [
        'canCreate' => has_capability('moodle/course:create', $context),
        'capability' => 'moodle/course:create',
        'context' => 'coursecat:' . $category,
    ];
}

function stage_course_self_enrolment_state(stdClass $course): array {
    $instance = null;
    foreach (enrol_get_instances((int)$course->id, false) as $candidate) {
        if (($candidate->enrol ?? '') === 'self') {
            $instance = $candidate;
            break;
        }
    }

    return [
        'pluginEnabled' => enrol_is_enabled('self'),
        'instanceId' => $instance ? (int)$instance->id : null,
        'enabled' => $instance ? (int)$instance->status === ENROL_INSTANCE_ENABLED : false,
        'newEnrolmentsAllowed' => $instance ? !empty($instance->customint6) : false,
    ];
}

function ensure_stage_course_self_enrolment(stdClass $course): array {
    if (!enrol_is_enabled('self')) {
        throw new RuntimeException('Moodle self enrolment is disabled at site level; the new Stage Course was not created.');
    }

    $plugin = enrol_get_plugin('self');
    if (!$plugin) {
        throw new RuntimeException('Moodle self enrolment plugin is not installed; the new Stage Course was not created.');
    }

    $instance = null;
    foreach (enrol_get_instances((int)$course->id, false) as $candidate) {
        if (($candidate->enrol ?? '') === 'self') {
            $instance = $candidate;
            break;
        }
    }

    if ($instance) {
        $data = clone $instance;
        $data->status = ENROL_INSTANCE_ENABLED;
        // customint6 is the self plugin's "Allow new enrolments" setting.
        $data->customint6 = 1;
        if (!$plugin->update_instance($instance, $data)) {
            throw new RuntimeException('Could not enable the existing self enrolment instance for the new Stage Course.');
        }
    } else {
        $fields = $plugin->get_instance_defaults();
        $fields['status'] = ENROL_INSTANCE_ENABLED;
        $fields['customint6'] = 1;
        if ($plugin->get_config('requirepassword')) {
            $fields['password'] = generate_password(20);
        }
        $instanceid = $plugin->add_instance($course, $fields);
        if (!$instanceid) {
            throw new RuntimeException('Could not add self enrolment to the new Stage Course.');
        }
    }

    $state = stage_course_self_enrolment_state($course);
    if (empty($state['enabled']) || empty($state['newEnrolmentsAllowed'])) {
        throw new RuntimeException('Self enrolment verification failed for the new Stage Course.');
    }
    return $state;
}

function create_stage_course(array $definition): stdClass {
    global $DB;

    $shortconflict = $DB->get_record('course', ['shortname' => $definition['courseShortname']], '*', IGNORE_MISSING);
    if ($shortconflict && (string)$shortconflict->idnumber !== (string)$definition['courseIdnumber']) {
        throw new RuntimeException('Expected shortname is already used by another course: ' . $definition['courseShortname']);
    }

    ensure_moodle_course_id_floor();

    $course = new stdClass();
    $course->fullname = $definition['courseFullname'];
    $course->shortname = $definition['courseShortname'];
    $course->idnumber = $definition['courseIdnumber'];
    $course->category = (int)$definition['moodleCategory'];
    $course->summary = '<p>FLW Stage Course created by Smart Course Editor S3 resolver.</p>';
    $course->summaryformat = FORMAT_HTML;
    $course->format = 'topics';
    $course->numsections = 0;
    $course->visible = 1;
    $course->newsitems = 0;
    $course->startdate = time();

    // Keep course creation and its required self-enrolment method atomic. This
    // avoids leaving behind a partially configured Stage Course if Moodle's
    // self enrolment plugin is unavailable or rejects the instance update.
    $transaction = $DB->start_delegated_transaction();
    $created = create_course($course);
    ensure_stage_course_self_enrolment($created);
    $transaction->allow_commit();
    return $created;
}

function resolve_stage_course_group(array $group, bool $dryrun, string $map_path, bool $create_if_missing = true): array {
    global $DB, $CFG;

    $definition = $group['definition'];
    $items = $group['items'] ?? [];
    $unitids = array_map(function($item) {
        $target = s3_target_metadata($item);
        return s3_clean_key($target['unitId'] ?? ('U' . ($item['unit'] ?? '')));
    }, $items);
    $unitids = array_values(array_filter($unitids));

    if (empty($definition['valid'])) {
        return [
            'status' => $definition['status'] ?? 'STAGE_UNRESOLVED',
            'courseAction' => $definition['status'] ?? 'STAGE_UNRESOLVED',
            'message' => $definition['message'] ?? 'Stage course definition is invalid.',
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'items' => $items,
        ];
    }

    $category_error = validate_stage_category($definition);
    $legacy = $category_error ? [] : find_legacy_unit_courses($definition, $items);
    if ($category_error) {
        return [
            'status' => 'CATEGORY_MISSING',
            'courseAction' => 'CATEGORY_MISSING',
            'message' => $category_error['message'],
            'definition' => $definition,
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => [],
        ];
    }

    $program_mapping = find_program1_stage_course_mapping($definition);
    if ($program_mapping) {
        $course = $program_mapping['course'];
        if (!stage_course_matches_definition($course, $definition)) {
            $conflict = stage_course_conflict($definition, $course, 'Existing FLW Program-1 mapping points to a course that does not match the S3 Stage Course definition.');
            $conflict['program1Mapping'] = $program_mapping['record'];
            $conflict['potentialConflicts'] = $legacy;
            return $conflict;
        }
        if (!$dryrun) {
            record_stage_course_mapping($definition, $course, 'REUSE_STAGE_COURSE', $map_path);
        }
        return [
            'status' => 'REUSE_STAGE_COURSE',
            'courseAction' => 'REUSE_STAGE_COURSE',
            'resolverSource' => 'PROGRAM1_MAPPING',
            'definition' => $definition,
            'course' => stage_course_summary_row($course),
            'courseUrl' => rtrim((string)$CFG->wwwroot, '/') . '/course/view.php?id=' . $course->id,
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => $legacy,
        ];
    }

    $idnumbermatches = $DB->get_records('course', ['idnumber' => $definition['courseIdnumber']], 'id ASC');
    if (count($idnumbermatches) > 1) {
        return [
            'status' => 'COURSE_IDNUMBER_CONFLICT',
            'courseAction' => 'COURSE_IDNUMBER_CONFLICT',
            'message' => 'Multiple Moodle courses use the same Stage Course idnumber; administrator resolution is required.',
            'definition' => $definition,
            'courses' => array_map(fn($matched) => stage_course_summary_row($matched), array_values($idnumbermatches)),
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => $legacy,
        ];
    }
    $course = $idnumbermatches ? reset($idnumbermatches) : false;
    if ($course) {
        if (!stage_course_matches_definition($course, $definition)) {
            $conflict = stage_course_conflict($definition, $course, 'A Moodle course already uses the Stage Course idnumber but does not match expected S3 name/category.');
            $conflict['unitIds'] = $unitids;
            $conflict['unitCount'] = count($items);
            $conflict['unitsPlannedForS4'] = count($items);
            $conflict['futureUnitAction'] = 'UNIT_SECTION_PENDING_S4';
            $conflict['potentialConflicts'] = $legacy;
            return $conflict;
        }
        if (!$dryrun) {
            record_stage_course_mapping($definition, $course, 'REUSE_STAGE_COURSE', $map_path);
        }
        return [
            'status' => 'REUSE_STAGE_COURSE',
            'courseAction' => 'REUSE_STAGE_COURSE',
            'resolverSource' => 'COURSE_IDNUMBER',
            'definition' => $definition,
            'course' => stage_course_summary_row($course),
            'courseUrl' => rtrim((string)$CFG->wwwroot, '/') . '/course/view.php?id=' . $course->id,
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => $legacy,
        ];
    }

    if (!$create_if_missing) {
        return [
            'status' => 'CREATE_STAGE_COURSE',
            'courseAction' => 'CREATE_STAGE_COURSE',
            'resolverSource' => 'NOT_FOUND',
            'definition' => $definition,
            'course' => null,
            'selfEnrolment' => [
                'action' => 'ENABLE_ON_CREATE',
                'enabled' => true,
                'newEnrolmentsAllowed' => true,
            ],
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => $legacy,
        ];
    }

    if ($dryrun) {
        $permission = stage_course_permission($definition);
        return [
            'status' => 'CREATE_STAGE_COURSE',
            'courseAction' => 'CREATE_STAGE_COURSE',
            'resolverSource' => 'NOT_FOUND',
            'definition' => $definition,
            'course' => null,
            'wouldCreate' => true,
            'permission' => $permission,
            'selfEnrolment' => [
                'action' => 'ENABLE_ON_CREATE',
                'enabled' => true,
                'newEnrolmentsAllowed' => true,
            ],
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => $legacy,
        ];
    }

    $permission = stage_course_permission($definition);
    if (empty($permission['canCreate'])) {
        return [
            'status' => 'PERMISSION_DENIED',
            'courseAction' => 'PERMISSION_DENIED',
            'message' => 'Current Moodle user cannot create a course in the configured category.',
            'definition' => $definition,
            'permission' => $permission,
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => $legacy,
        ];
    }

    try {
        $created = create_stage_course($definition);
        record_stage_course_mapping($definition, $created, 'CREATE_STAGE_COURSE', $map_path);
        return [
            'status' => 'CREATE_STAGE_COURSE',
            'courseAction' => 'CREATE_STAGE_COURSE',
            'resolverSource' => 'CREATED',
            'definition' => $definition,
            'course' => stage_course_summary_row($created),
            'courseUrl' => rtrim((string)$CFG->wwwroot, '/') . '/course/view.php?id=' . $created->id,
            'created' => true,
            'selfEnrolment' => stage_course_self_enrolment_state($created),
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => $legacy,
        ];
    } catch (Throwable $e) {
        return [
            'status' => 'COURSE_CREATE_FAILED',
            'courseAction' => 'COURSE_CREATE_FAILED',
            'message' => $e->getMessage(),
            'class' => get_class($e),
            'definition' => $definition,
            'unitIds' => $unitids,
            'unitCount' => count($items),
            'unitsPlannedForS4' => count($items),
            'futureUnitAction' => 'UNIT_SECTION_PENDING_S4',
            'potentialConflicts' => $legacy,
        ];
    }
}

function stage_result_public_row(array $resolution): array {
    $definition = $resolution['definition'] ?? [];
    $course = $resolution['course'] ?? null;
    $courseid = is_array($course) ? ($course['courseId'] ?? null) : null;
    return [
        'status' => $resolution['status'] ?? '',
        'courseAction' => $resolution['courseAction'] ?? ($resolution['status'] ?? ''),
        'resolverSource' => $resolution['resolverSource'] ?? '',
        'worldCode' => $definition['worldCode'] ?? '',
        'worldTitle' => $definition['worldTitle'] ?? '',
        'deploymentStageCode' => $definition['deploymentStageCode'] ?? '',
        'courseExternalKey' => $definition['courseExternalKey'] ?? '',
        'courseIdnumber' => $definition['courseIdnumber'] ?? '',
        'courseFullname' => $definition['courseFullname'] ?? '',
        'courseShortname' => $definition['courseShortname'] ?? '',
        'courseCategory' => $definition['moodleCategory'] ?? null,
        'courseId' => $courseid,
        'courseUrl' => $resolution['courseUrl'] ?? '',
        'unitIds' => $resolution['unitIds'] ?? [],
        'unitCount' => $resolution['unitCount'] ?? 0,
        'unitsPlannedForS4' => $resolution['unitsPlannedForS4'] ?? 0,
        'futureUnitAction' => $resolution['futureUnitAction'] ?? 'UNIT_SECTION_PENDING_S4',
        'message' => $resolution['message'] ?? '',
        'conflictCourses' => $resolution['courses'] ?? [],
        'potentialConflicts' => $resolution['potentialConflicts'] ?? [],
        'permission' => $resolution['permission'] ?? null,
        'courseImage' => $resolution['courseImage'] ?? null,
    ];
}

function stage_course_summary(array $results): array {
    $counts = [];
    $imagecounts = [];
    $legacy = 0;
    foreach ($results as $row) {
        $status = $row['status'] ?? 'UNKNOWN';
        $counts[$status] = ($counts[$status] ?? 0) + 1;
        $imagestatus = (string)($row['courseImage']['status'] ?? '');
        if ($imagestatus !== '') {
            $imagecounts[$imagestatus] = ($imagecounts[$imagestatus] ?? 0) + 1;
        }
        $legacy += count(array_filter($row['potentialConflicts'] ?? [], fn($conflict) => ($conflict['status'] ?? '') === 'LEGACY_UNIT_COURSE_FOUND'));
    }
    $blocking = ['COURSE_IDNUMBER_CONFLICT', 'CATEGORY_MISSING', 'STAGE_UNRESOLVED', 'STAGE_CONFLICT', 'PERMISSION_DENIED', 'COURSE_CREATE_FAILED'];
    return [
        'stageCourseCount' => count($results),
        'reusedStageCourses' => $counts['REUSE_STAGE_COURSE'] ?? 0,
        'createdStageCourses' => count(array_filter($results, fn($row) => ($row['status'] ?? '') === 'CREATE_STAGE_COURSE' && !empty($row['courseId']))),
        'wouldCreateStageCourses' => count(array_filter($results, fn($row) => ($row['status'] ?? '') === 'CREATE_STAGE_COURSE' && empty($row['courseId']))),
        'conflictCount' => array_sum(array_intersect_key($counts, array_flip($blocking))),
        'legacyUnitCoursesFound' => $legacy,
        'statusCounts' => $counts,
        'courseImageStatusCounts' => $imagecounts,
        'courseImagesSet' => $imagecounts['SET_COURSE_IMAGE'] ?? 0,
        'courseImagesUpdated' => $imagecounts['UPDATE_COURSE_IMAGE'] ?? 0,
        'courseImagesUnchanged' => $imagecounts['COURSE_IMAGE_UNCHANGED'] ?? 0,
        'courseImagesWouldSet' => ($imagecounts['WOULD_SET_COURSE_IMAGE'] ?? 0) + ($imagecounts['WOULD_SET_COURSE_IMAGE_ON_CREATE'] ?? 0),
        'courseImagesWouldUpdate' => $imagecounts['WOULD_UPDATE_COURSE_IMAGE'] ?? 0,
        'courseImagesPendingExport' => $imagecounts['COURSE_IMAGE_PENDING_EXPORT'] ?? 0,
        'courseImagesMissing' => $imagecounts['NO_UNIT_IMAGE'] ?? 0,
        'courseImageFailures' => array_sum(array_filter($imagecounts, fn($count, $status) => course_image_failure_status((string)$status), ARRAY_FILTER_USE_BOTH)),
        'unitSectionsCreated' => 0,
        'scormActivitiesImported' => 0,
    ];
}

function unit_section_map_path(?string $path = null): string {
    if ($path && trim($path) !== '') {
        return $path;
    }
    return dirname(__DIR__) . DIRECTORY_SEPARATOR . 'flw_moodle_unit_section_map.json';
}

function load_unit_section_map(string $path): array {
    if (!file_exists($path)) {
        return ['schemaVersion' => 1, 'unitSections' => []];
    }
    $json = file_get_contents($path);
    $data = json_decode($json ?: '', true);
    if (!is_array($data)) {
        return ['schemaVersion' => 1, 'unitSections' => []];
    }
    if (!isset($data['unitSections']) || !is_array($data['unitSections'])) {
        $data['unitSections'] = [];
    }
    return $data;
}

function save_unit_section_map(string $path, array $map): void {
    $dir = dirname($path);
    if (!is_dir($dir) && !mkdir($dir, 0777, true) && !is_dir($dir)) {
        throw new RuntimeException('Cannot create unit section map directory: ' . $dir);
    }
    file_put_contents($path, json_out($map));
}

function s4_unit_number_string(array $definition): string {
    $number = (string)($definition['unitNumber'] ?? '');
    $digits = preg_replace('/\D+/', '', $number);
    if ($digits !== '') {
        return sprintf('%03d', (int)$digits);
    }
    $sequence = (int)($definition['unitSequence'] ?? 0);
    return $sequence > 0 ? sprintf('%03d', $sequence) : '000';
}

function unit_section_definition(array $item): array {
    $stage = stage_course_definition($item);
    if (empty($stage['valid'])) {
        return [
            'valid' => false,
            'status' => $stage['status'] ?? 'STAGE_UNRESOLVED',
            'message' => $stage['message'] ?? 'Stage course definition is invalid.',
            'stageDefinition' => $stage,
            'item' => $item,
        ];
    }
    $target = $stage['target'] ?? s3_target_metadata($item);
    $unitsequence = (int)($stage['unitSequence'] ?? $target['unitSequence'] ?? item_unit_number($item));
    $unitnumber = s3_clean_key($stage['unitNumber'] ?? $target['unitNumber'] ?? sprintf('%03d', $unitsequence));
    $unitid = s3_clean_key($stage['unitId'] ?? $target['unitId'] ?? ($stage['worldCode'] . '-U' . sprintf('%03d', $unitsequence)));
    $unittitle = s3_clean_key($stage['unitTitle'] ?? $target['unitTitle'] ?? $item['title'] ?? $item['label'] ?? ('Unit ' . s4_unit_number_string(['unitNumber' => $unitnumber, 'unitSequence' => $unitsequence])));
    $sectionname = clean_short_text('U' . s4_unit_number_string(['unitNumber' => $unitnumber, 'unitSequence' => $unitsequence]) . ' — ' . $unittitle, 255);

    return [
        'valid' => true,
        'status' => 'RESOLVED',
        'WorldCode' => $stage['worldCode'],
        'DeploymentStageCode' => $stage['deploymentStageCode'],
        'courseExternalKey' => $stage['courseExternalKey'],
        'courseIdnumber' => $stage['courseIdnumber'],
        'courseShortname' => $stage['courseShortname'],
        'UnitID' => $unitid,
        'unitNumber' => $unitnumber,
        'unitSequence' => $unitsequence,
        'unitTitle' => $unittitle,
        'expectedSectionName' => $sectionname,
        'target' => $target,
        'stageDefinition' => $stage,
        'item' => $item,
    ];
}

function flw_unit_marker_regex(): string {
    return '/<!--\s*FLW_UNIT_SECTION_MARKER_START\s*-->.*?<!--\s*FLW_UNIT_SECTION_MARKER_END\s*-->/is';
}

function flw_unit_marker_value(string $value): string {
    return str_replace(['--', '<', '>'], ['-', '', ''], trim($value));
}

function flw_unit_marker_block(array $definition): string {
    $pairs = [
        'FLW_UNIT_KEY' => $definition['UnitID'] ?? '',
        'FLW_WORLD_CODE' => $definition['WorldCode'] ?? '',
        'FLW_DEPLOYMENT_STAGE' => $definition['DeploymentStageCode'] ?? '',
        'FLW_COURSE_KEY' => $definition['courseExternalKey'] ?? '',
        'FLW_UNIT_SEQUENCE' => (string)($definition['unitSequence'] ?? ''),
    ];
    $lines = ['<!-- FLW_UNIT_SECTION_MARKER_START -->'];
    foreach ($pairs as $key => $value) {
        $lines[] = '<!-- ' . $key . ':' . flw_unit_marker_value((string)$value) . ' -->';
    }
    $lines[] = '<!-- FLW_UNIT_SECTION_MARKER_END -->';
    return implode("\n", $lines);
}

function extract_flw_unit_marker(?string $summary): ?array {
    $summary = (string)$summary;
    if (!preg_match(flw_unit_marker_regex(), $summary, $match)) {
        return null;
    }
    $block = $match[0];
    $fields = [
        'FLW_UNIT_KEY' => 'UnitID',
        'FLW_WORLD_CODE' => 'WorldCode',
        'FLW_DEPLOYMENT_STAGE' => 'DeploymentStageCode',
        'FLW_COURSE_KEY' => 'courseExternalKey',
        'FLW_UNIT_SEQUENCE' => 'unitSequence',
    ];
    $marker = ['raw' => $block];
    foreach ($fields as $source => $target) {
        if (preg_match('/' . preg_quote($source, '/') . '\s*:\s*([^<\r\n]+)/i', $block, $m)) {
            $value = trim(preg_replace('/\s*-->\s*$/', '', trim($m[1])));
            $marker[$target] = $target === 'unitSequence' ? (int)$value : $value;
        }
    }
    return $marker;
}

function summary_with_unit_marker(?string $summary, array $definition): string {
    $summary = (string)$summary;
    $summary = preg_replace(flw_unit_marker_regex(), '', $summary);
    $summary = rtrim($summary);
    $marker = flw_unit_marker_block($definition);
    return $summary === '' ? $marker : ($summary . "\n\n" . $marker);
}

function unit_section_summary_row(stdClass $section): array {
    $marker = extract_flw_unit_marker($section->summary ?? '');
    return [
        'sectionId' => (int)$section->id,
        'courseId' => (int)$section->course,
        'sectionNumber' => (int)$section->section,
        'sectionName' => (string)($section->name ?? ''),
        'summaryLength' => strlen((string)($section->summary ?? '')),
        'summaryHasMarker' => $marker !== null,
        'marker' => $marker,
        'sequence' => (string)($section->sequence ?? ''),
        'visible' => (int)($section->visible ?? 1),
    ];
}

function unit_section_permission(stdClass $course): array {
    $context = context_course::instance((int)$course->id);
    return [
        'canUpdate' => has_capability('moodle/course:update', $context),
        'canMove' => has_capability('moodle/course:movesections', $context),
        'updateCapability' => 'moodle/course:update',
        'moveCapability' => 'moodle/course:movesections',
        'context' => 'course:' . (int)$course->id,
    ];
}

function record_unit_section_mapping(array $definition, stdClass $course, stdClass $section, string $status, string $map_path): void {
    $map = load_unit_section_map($map_path);
    $key = $definition['UnitID'];
    $existing = $map['unitSections'][$key] ?? [];
    $now = date('c');
    $map['unitSections'][$key] = [
        'UnitID' => $definition['UnitID'],
        'WorldCode' => $definition['WorldCode'],
        'DeploymentStageCode' => $definition['DeploymentStageCode'],
        'courseExternalKey' => $definition['courseExternalKey'],
        'moodleCourseId' => (int)$course->id,
        'moodleSectionId' => (int)$section->id,
        'moodleSectionNumber' => (int)$section->section,
        'unitNumber' => $definition['unitNumber'],
        'unitSequence' => (int)$definition['unitSequence'],
        'unitTitle' => $definition['unitTitle'],
        'sectionName' => $definition['expectedSectionName'],
        'status' => $status,
        'markerMethod' => 'COURSE_SECTION_SUMMARY_HTML_COMMENT',
        'createdAt' => $existing['createdAt'] ?? $now,
        'updatedAt' => $now,
    ];
    save_unit_section_map($map_path, $map);
}

function find_marker_sections_by_unit_id(string $unitid): array {
    global $DB;

    $records = $DB->get_records_sql(
        "SELECT id,course,section,name,summary,sequence,visible
           FROM {course_sections}
          WHERE summary LIKE :marker
       ORDER BY course ASC, section ASC, id ASC",
        ['marker' => '%FLW_UNIT_KEY:' . $unitid . '%']
    );
    return array_values($records);
}

function flw_unit_sections_for_course(int $courseid): array {
    global $DB;

    $sections = $DB->get_records('course_sections', ['course' => $courseid], 'section ASC, id ASC', 'id,course,section,name,summary,sequence,visible');
    $rows = [];
    foreach ($sections as $section) {
        $marker = extract_flw_unit_marker($section->summary ?? '');
        if ($marker && !empty($marker['UnitID'])) {
            $rows[] = ['section' => $section, 'marker' => $marker];
        }
    }
    return $rows;
}

function mapped_unit_section_record(array $definition, int $courseid, string $map_path): ?array {
    global $DB;

    $map = load_unit_section_map($map_path);
    $entry = $map['unitSections'][$definition['UnitID']] ?? null;
    if (!$entry) {
        return null;
    }
    $mappedcourseid = (int)($entry['moodleCourseId'] ?? 0);
    if ($mappedcourseid > 0 && $mappedcourseid !== $courseid) {
        return ['status' => 'UNIT_STAGE_MOVE_REQUIRED', 'entry' => $entry, 'section' => null];
    }
    $mappedkey = (string)($entry['courseExternalKey'] ?? '');
    if ($mappedkey !== '' && $mappedkey !== (string)$definition['courseExternalKey']) {
        return ['status' => 'UNIT_STAGE_MOVE_REQUIRED', 'entry' => $entry, 'section' => null];
    }
    $sectionid = (int)($entry['moodleSectionId'] ?? 0);
    if ($sectionid <= 0) {
        return ['status' => 'UNIT_SECTION_TARGET_MISSING', 'entry' => $entry, 'section' => null];
    }
    $section = $DB->get_record('course_sections', ['id' => $sectionid], 'id,course,section,name,summary,sequence,visible', IGNORE_MISSING);
    if (!$section) {
        return ['status' => 'UNIT_SECTION_TARGET_MISSING', 'entry' => $entry, 'section' => null];
    }
    if ((int)$section->course !== $courseid) {
        return ['status' => 'UNIT_STAGE_MOVE_REQUIRED', 'entry' => $entry, 'section' => $section];
    }
    return ['status' => 'FOUND', 'entry' => $entry, 'section' => $section];
}

function mapping_predates_recreated_course(stdClass $course, array $entry): bool {
    $mappedat = strtotime((string)($entry['updatedAt'] ?? $entry['createdAt'] ?? ''));
    $coursecreated = (int)($course->timecreated ?? 0);
    return $mappedat !== false && $mappedat > 0 && $coursecreated > $mappedat;
}

function unit_section_base_public(array $definition, array $stage_resolution, ?stdClass $course): array {
    global $CFG;

    $courseinfo = $stage_resolution['course'] ?? null;
    $courseid = $course ? (int)$course->id : (is_array($courseinfo) ? ($courseinfo['courseId'] ?? null) : null);
    return [
        'label' => $definition['item']['label'] ?? '',
        'unit' => $definition['item']['unit'] ?? '',
        'unitId' => $definition['UnitID'] ?? '',
        'unitNumber' => $definition['unitNumber'] ?? '',
        'unitSequence' => $definition['unitSequence'] ?? null,
        'unitTitle' => $definition['unitTitle'] ?? '',
        'worldCode' => $definition['WorldCode'] ?? '',
        'deploymentStageCode' => $definition['DeploymentStageCode'] ?? '',
        'courseExternalKey' => $definition['courseExternalKey'] ?? '',
        'courseId' => $courseid,
        'courseAction' => $stage_resolution['courseAction'] ?? ($stage_resolution['status'] ?? ''),
        'courseUrl' => $courseid ? rtrim((string)$CFG->wwwroot, '/') . '/course/view.php?id=' . $courseid : '',
        'expectedSectionName' => $definition['expectedSectionName'] ?? '',
        'markerMethod' => 'COURSE_SECTION_SUMMARY_HTML_COMMENT',
        'mappingMethod' => 'LOCAL_JSON_WITH_MARKER_FALLBACK',
        'manualTeacherContent' => 'PRESERVED',
        'scormAction' => 'SCORM_PENDING_S5',
        'scormActivitiesImported' => 0,
    ];
}

function section_result_with_status(array $definition, array $stage_resolution, ?stdClass $course, string $status, string $message = '', array $extra = []): array {
    return array_merge(unit_section_base_public($definition, $stage_resolution, $course), [
        'status' => $status,
        'sectionAction' => $status,
        'message' => $message,
    ], $extra);
}

function resolve_unit_section(array $item, array $stage_resolution, bool $dryrun, string $map_path): array {
    global $DB, $CFG;

    $definition = unit_section_definition($item);
    if (empty($definition['valid'])) {
        return [
            'label' => $item['label'] ?? '',
            'unit' => $item['unit'] ?? '',
            'unitId' => s3_target_metadata($item)['unitId'] ?? '',
            'status' => 'COURSE_NOT_RESOLVED',
            'sectionAction' => 'COURSE_NOT_RESOLVED',
            'courseAction' => $stage_resolution['courseAction'] ?? ($stage_resolution['status'] ?? ''),
            'message' => $definition['message'] ?? 'Stage Course is not resolved.',
            'scormAction' => 'SCORM_PENDING_S5',
            'scormActivitiesImported' => 0,
        ];
    }

    $courseinfo = $stage_resolution['course'] ?? null;
    $courseid = is_array($courseinfo) ? (int)($courseinfo['courseId'] ?? 0) : 0;
    $course = $courseid > 0 ? $DB->get_record('course', ['id' => $courseid], '*', IGNORE_MISSING) : false;
    if (!$course) {
        if ($dryrun && (($stage_resolution['courseAction'] ?? $stage_resolution['status'] ?? '') === 'CREATE_STAGE_COURSE')) {
            return section_result_with_status($definition, $stage_resolution, null, 'CREATE_SECTION', 'Unit Section would be created after the missing Stage Course is created.', [
                'wouldCreate' => true,
                'expectedSectionNumber' => 1,
                'expectedSectionName' => $definition['expectedSectionName'] ?? '',
            ]);
        }
        return section_result_with_status($definition, $stage_resolution, null, 'COURSE_NOT_RESOLVED', 'Stage Course must exist before the Unit Section can be resolved.');
    }

    $markers = find_marker_sections_by_unit_id($definition['UnitID']);
    $targetmarkers = array_values(array_filter($markers, fn($section) => (int)$section->course === (int)$course->id));
    $othermarkers = array_values(array_filter($markers, fn($section) => (int)$section->course !== (int)$course->id));
    $mapped = mapped_unit_section_record($definition, (int)$course->id, $map_path);
    $mappingrecovery = [];

    if ($mapped && $mapped['status'] === 'UNIT_STAGE_MOVE_REQUIRED') {
        return section_result_with_status($definition, $stage_resolution, $course, 'UNIT_STAGE_MOVE_REQUIRED', 'Existing Unit→Section mapping points to a different Stage Course.', [
            'mappedEntry' => $mapped['entry'],
            'mappedSection' => $mapped['section'] ? unit_section_summary_row($mapped['section']) : null,
        ]);
    }
    if ($othermarkers) {
        return section_result_with_status($definition, $stage_resolution, $course, 'UNIT_STAGE_MOVE_REQUIRED', 'Existing Unit marker is in a different Stage Course; migration must be explicit.', [
            'conflictSections' => array_map(fn($section) => unit_section_summary_row($section), $othermarkers),
        ]);
    }
    if (count($targetmarkers) > 1) {
        return section_result_with_status($definition, $stage_resolution, $course, 'UNIT_SECTION_DUPLICATE', 'Multiple Moodle sections in the Stage Course contain the same FLW Unit marker.', [
            'conflictSections' => array_map(fn($section) => unit_section_summary_row($section), $targetmarkers),
        ]);
    }
    if ($mapped && $mapped['status'] === 'UNIT_SECTION_TARGET_MISSING') {
        if (mapping_predates_recreated_course($course, $mapped['entry'])) {
            $mappingrecovery = [
                'staleSectionMappingRecovered' => true,
                'staleMappingReason' => 'STAGE_COURSE_RECREATED_AFTER_MAPPING',
                'previousMappedSectionId' => (int)($mapped['entry']['moodleSectionId'] ?? 0),
                'previousMappingUpdatedAt' => (string)($mapped['entry']['updatedAt'] ?? ''),
                'currentCourseCreatedAt' => date('c', (int)$course->timecreated),
            ];
            $mapped = null;
        } else {
            return section_result_with_status($definition, $stage_resolution, $course, 'UNIT_SECTION_TARGET_MISSING', 'Local Unit→Section mapping points to a section that no longer exists.', [
                'mappedEntry' => $mapped['entry'],
            ]);
        }
    }

    $section = null;
    if ($mapped && $mapped['status'] === 'FOUND') {
        $section = $mapped['section'];
    }
    if ($section && count($targetmarkers) === 1 && (int)$targetmarkers[0]->id !== (int)$section->id) {
        return section_result_with_status($definition, $stage_resolution, $course, 'SECTION_MAPPING_CONFLICT', 'Local map and Moodle marker point to different sections.', [
            'mappedSection' => unit_section_summary_row($section),
            'markerSection' => unit_section_summary_row($targetmarkers[0]),
        ]);
    }
    if (!$section && count($targetmarkers) === 1) {
        $section = $targetmarkers[0];
    }

    $permission = unit_section_permission($course);
    if (!$section) {
        $existing = $DB->get_records('course_sections', ['course' => (int)$course->id], 'section DESC', 'id,section', 0, 1);
        $last = $existing ? reset($existing) : null;
        $nextnumber = max(1, $last ? ((int)$last->section + 1) : 1);
        if ($dryrun) {
            return section_result_with_status($definition, $stage_resolution, $course, 'CREATE_SECTION', $mappingrecovery ? 'Unit Section would be recreated and its stale local mapping replaced.' : 'Unit Section would be created.', array_merge([
                'wouldCreate' => true,
                'expectedSectionNumber' => $nextnumber,
                'permission' => $permission,
            ], $mappingrecovery));
        }
        if (empty($permission['canUpdate'])) {
            return section_result_with_status($definition, $stage_resolution, $course, 'PERMISSION_DENIED', 'Current Moodle user cannot create/update course sections.', array_merge([
                'permission' => $permission,
            ], $mappingrecovery));
        }
        try {
            $transaction = $DB->start_delegated_transaction();
            course_create_sections_if_missing($course, $nextnumber);
            $section = $DB->get_record('course_sections', ['course' => (int)$course->id, 'section' => $nextnumber], 'id,course,section,name,summary,sequence,visible', MUST_EXIST);
            course_update_section($course, $section, (object)[
                'name' => $definition['expectedSectionName'],
                'summary' => summary_with_unit_marker('', $definition),
                'summaryformat' => FORMAT_HTML,
                'visible' => 1,
            ]);
            $transaction->allow_commit();
            rebuild_course_cache((int)$course->id, true);
            $section = $DB->get_record('course_sections', ['id' => (int)$section->id], 'id,course,section,name,summary,sequence,visible', MUST_EXIST);
            record_unit_section_mapping($definition, $course, $section, 'CREATE_SECTION', $map_path);
            return section_result_with_status($definition, $stage_resolution, $course, 'CREATE_SECTION', $mappingrecovery ? 'Unit Section recreated; stale local mapping replaced.' : 'Unit Section created.', array_merge([
                'created' => true,
                'sectionId' => (int)$section->id,
                'sectionNumber' => (int)$section->section,
                'sectionName' => (string)$section->name,
                'sectionUrl' => rtrim((string)$CFG->wwwroot, '/') . '/course/view.php?id=' . $course->id . '#section-' . (int)$section->section,
                'permission' => $permission,
            ], $mappingrecovery));
        } catch (Throwable $e) {
            return section_result_with_status($definition, $stage_resolution, $course, 'SECTION_CREATE_FAILED', $e->getMessage(), array_merge([
                'class' => get_class($e),
            ], $mappingrecovery));
        }
    }

    $expectedsummary = summary_with_unit_marker((string)($section->summary ?? ''), $definition);
    $needsname = (string)($section->name ?? '') !== (string)$definition['expectedSectionName'];
    $needssummary = (string)($section->summary ?? '') !== $expectedsummary;
    if ($needsname || $needssummary) {
        if ($dryrun) {
            return section_result_with_status($definition, $stage_resolution, $course, 'UPDATE_SECTION', 'Unit Section would be updated to match title/marker while preserving teacher summary content.', [
                'wouldUpdate' => true,
                'sectionId' => (int)$section->id,
                'sectionNumber' => (int)$section->section,
                'sectionName' => (string)$section->name,
                'expectedSectionName' => $definition['expectedSectionName'],
                'needsNameUpdate' => $needsname,
                'needsMarkerUpdate' => $needssummary,
                'permission' => $permission,
            ]);
        }
        if (empty($permission['canUpdate'])) {
            return section_result_with_status($definition, $stage_resolution, $course, 'PERMISSION_DENIED', 'Current Moodle user cannot create/update course sections.', [
                'sectionId' => (int)$section->id,
                'sectionNumber' => (int)$section->section,
                'permission' => $permission,
            ]);
        }
        try {
            course_update_section($course, $section, (object)[
                'name' => $definition['expectedSectionName'],
                'summary' => $expectedsummary,
                'summaryformat' => FORMAT_HTML,
            ]);
            rebuild_course_cache((int)$course->id, true);
            $section = $DB->get_record('course_sections', ['id' => (int)$section->id], 'id,course,section,name,summary,sequence,visible', MUST_EXIST);
            record_unit_section_mapping($definition, $course, $section, 'UPDATE_SECTION', $map_path);
            return section_result_with_status($definition, $stage_resolution, $course, 'UPDATE_SECTION', 'Unit Section title/marker updated; teacher summary content preserved.', [
                'updated' => true,
                'sectionId' => (int)$section->id,
                'sectionNumber' => (int)$section->section,
                'sectionName' => (string)$section->name,
                'sectionUrl' => rtrim((string)$CFG->wwwroot, '/') . '/course/view.php?id=' . $course->id . '#section-' . (int)$section->section,
                'needsNameUpdate' => $needsname,
                'needsMarkerUpdate' => $needssummary,
                'permission' => $permission,
            ]);
        } catch (Throwable $e) {
            return section_result_with_status($definition, $stage_resolution, $course, 'SECTION_UPDATE_FAILED', $e->getMessage(), [
                'class' => get_class($e),
                'sectionId' => (int)$section->id,
                'sectionNumber' => (int)$section->section,
            ]);
        }
    }

    if (!$dryrun) {
        record_unit_section_mapping($definition, $course, $section, 'REUSE_SECTION', $map_path);
    }
    return section_result_with_status($definition, $stage_resolution, $course, 'REUSE_SECTION', 'Unit Section already matches canonical identity.', [
        'sectionId' => (int)$section->id,
        'sectionNumber' => (int)$section->section,
        'sectionName' => (string)$section->name,
        'sectionUrl' => rtrim((string)$CFG->wwwroot, '/') . '/course/view.php?id=' . $course->id . '#section-' . (int)$section->section,
        'permission' => $permission,
    ]);
}

function enforce_unit_section_order(stdClass $course, bool $dryrun): array {
    global $DB;

    $rows = flw_unit_sections_for_course((int)$course->id);
    usort($rows, function($a, $b) {
        $aseq = (int)($a['marker']['unitSequence'] ?? 0);
        $bseq = (int)($b['marker']['unitSequence'] ?? 0);
        if ($aseq === $bseq) {
            return strcmp((string)$a['marker']['UnitID'], (string)$b['marker']['UnitID']);
        }
        return $aseq <=> $bseq;
    });
    $moves = [];
    $desired = 1;
    foreach ($rows as $row) {
        $section = $DB->get_record('course_sections', ['id' => (int)$row['section']->id], 'id,course,section,name,summary,sequence,visible', IGNORE_MISSING);
        if (!$section) {
            continue;
        }
        if ((int)$section->section !== $desired) {
            $marker = extract_flw_unit_marker($section->summary ?? '') ?: $row['marker'];
            $move = [
                'UnitID' => $marker['UnitID'] ?? '',
                'sectionId' => (int)$section->id,
                'fromSectionNumber' => (int)$section->section,
                'toSectionNumber' => $desired,
                'status' => 'REORDER_SECTION',
            ];
            if (!$dryrun) {
                $permission = unit_section_permission($course);
                if (empty($permission['canMove'])) {
                    $move['status'] = 'PERMISSION_DENIED';
                    $move['permission'] = $permission;
                    $moves[] = $move;
                    $desired++;
                    continue;
                }
                $ok = move_section_to($course, (int)$section->section, $desired, true);
                if (!$ok) {
                    $move['status'] = 'SECTION_REORDER_FAILED';
                } else {
                    $after = $DB->get_record('course_sections', ['id' => (int)$section->id], 'id,course,section,name,summary,sequence,visible', IGNORE_MISSING);
                    if ($after) {
                        $move['sectionNumber'] = (int)$after->section;
                    }
                }
            } else {
                $move['wouldReorder'] = true;
            }
            $moves[] = $move;
        }
        $desired++;
    }
    return $moves;
}

function apply_order_moves_to_unit_results(array $unitresults, array $moves): array {
    global $DB, $CFG;

    $movesbyunit = [];
    foreach ($moves as $move) {
        if (!empty($move['UnitID'])) {
            $movesbyunit[$move['UnitID']] = $move;
        }
    }
    foreach ($unitresults as &$row) {
        $unitid = (string)($row['unitId'] ?? '');
        if ($unitid !== '' && isset($movesbyunit[$unitid])) {
            $row['orderAction'] = $movesbyunit[$unitid]['status'];
            $row['reorder'] = $movesbyunit[$unitid];
            if (($row['status'] ?? '') === 'REUSE_SECTION' && $movesbyunit[$unitid]['status'] === 'REORDER_SECTION') {
                $row['status'] = 'REORDER_SECTION';
                $row['sectionAction'] = 'REORDER_SECTION';
                $row['message'] = 'Unit Section reused and reordered into canonical Unit sequence.';
            }
        } else {
            $row['orderAction'] = 'NO_REORDER';
        }
        if (!empty($row['sectionId'])) {
            $section = $DB->get_record('course_sections', ['id' => (int)$row['sectionId']], 'id,course,section,name', IGNORE_MISSING);
            if ($section) {
                $row['sectionNumber'] = (int)$section->section;
                $row['sectionName'] = (string)$section->name;
                $row['sectionUrl'] = !empty($row['courseId'])
                    ? rtrim((string)$CFG->wwwroot, '/') . '/course/view.php?id=' . (int)$row['courseId'] . '#section-' . (int)$section->section
                    : ($row['sectionUrl'] ?? '');
            }
        }
    }
    unset($row);
    return $unitresults;
}

function unit_section_rows_have_blockers(array $unitresults): bool {
    $blocking = [
        'COURSE_NOT_RESOLVED',
        'UNIT_SECTION_DUPLICATE',
        'UNIT_SECTION_TARGET_MISSING',
        'UNIT_STAGE_MOVE_REQUIRED',
        'SECTION_MAPPING_CONFLICT',
        'PERMISSION_DENIED',
        'SECTION_CREATE_FAILED',
        'SECTION_UPDATE_FAILED',
    ];
    foreach ($unitresults as $row) {
        if (in_array(($row['status'] ?? ''), $blocking, true)) {
            return true;
        }
    }
    return false;
}

function refresh_unit_section_group_mappings(array $items, array $unitresults, stdClass $course, string $map_path): void {
    global $DB;

    foreach ($unitresults as $index => $row) {
        if (empty($row['sectionId']) || unit_section_rows_have_blockers([$row])) {
            continue;
        }
        if (!isset($items[$index])) {
            continue;
        }
        $definition = unit_section_definition($items[$index]);
        if (empty($definition['valid'])) {
            continue;
        }
        $section = $DB->get_record('course_sections', ['id' => (int)$row['sectionId']], 'id,course,section,name,summary,sequence,visible', IGNORE_MISSING);
        if ($section && (int)$section->course === (int)$course->id) {
            record_unit_section_mapping($definition, $course, $section, (string)($row['status'] ?? 'REUSE_SECTION'), $map_path);
        }
    }
}

function unit_scorm_map_path(?string $path = null): string {
    if ($path && trim($path) !== '') {
        return $path;
    }
    return dirname(__DIR__) . DIRECTORY_SEPARATOR . 'flw_moodle_unit_scorm_map.json';
}

function load_unit_scorm_map(string $path): array {
    if (!file_exists($path)) {
        return ['schemaVersion' => 1, 'unitScormActivities' => []];
    }
    $json = file_get_contents($path);
    $data = json_decode($json ?: '', true);
    if (!is_array($data)) {
        return ['schemaVersion' => 1, 'unitScormActivities' => []];
    }
    if (!isset($data['unitScormActivities']) || !is_array($data['unitScormActivities'])) {
        $data['unitScormActivities'] = [];
    }
    return $data;
}

function save_unit_scorm_map(string $path, array $map): void {
    $dir = dirname($path);
    if (!is_dir($dir) && !mkdir($dir, 0777, true) && !is_dir($dir)) {
        throw new RuntimeException('Cannot create unit SCORM map directory: ' . $dir);
    }
    file_put_contents($path, json_out($map));
}

function s5_identifier_segment($value): string {
    $clean = strtoupper(preg_replace('/[^A-Za-z0-9]+/', '_', trim((string)($value ?? ''))));
    return trim($clean, '_');
}

function s5_unit_number_for_identifier(array $definition): string {
    return s4_unit_number_string([
        'unitNumber' => $definition['unitNumber'] ?? '',
        'unitSequence' => $definition['unitSequence'] ?? 0,
    ]);
}

function s5_default_stable_cmidnumber(array $definition): string {
    return clean_short_text('FLW_' . s5_identifier_segment($definition['WorldCode'] ?? '') .
        '_U' . s5_unit_number_for_identifier($definition) . '_UNITSCORM', 100);
}

function s5_default_manifest_identifier(array $definition): string {
    return clean_short_text('FLW_' . s5_identifier_segment($definition['WorldCode'] ?? '') .
        '_U' . s5_unit_number_for_identifier($definition) . '_SCORM12', 255);
}

function s5_first_array_value(array $sources, string $key): array {
    foreach ($sources as $source) {
        if (is_array($source) && isset($source[$key]) && is_array($source[$key]) && count($source[$key]) > 0) {
            return $source[$key];
        }
    }
    return [];
}

function s5_first_string_value(array $sources, string $key): string {
    foreach ($sources as $source) {
        if (is_array($source) && isset($source[$key]) && trim((string)$source[$key]) !== '') {
            return trim((string)$source[$key]);
        }
    }
    return '';
}

function unit_scorm_definition(array $item): array {
    $unit = unit_section_definition($item);
    if (empty($unit['valid'])) {
        return [
            'valid' => false,
            'status' => $unit['status'] ?? 'COURSE_NOT_RESOLVED',
            'message' => $unit['message'] ?? 'Unit Section definition is invalid.',
            'unitDefinition' => $unit,
            'item' => $item,
        ];
    }

    $target = $unit['target'] ?? s3_target_metadata($item);
    $export = (isset($item['export']) && is_array($item['export'])) ? $item['export'] : [];
    $sources = [$target, $item, $export];
    $activityid = s5_first_string_value($sources, 'scormActivityExternalKey');
    if ($activityid === '') {
        $activityid = ($unit['UnitID'] ?? '') . '-UNITSCORM';
    }
    $stablecmidnumber = s5_first_string_value($sources, 'futureCmidNumber');
    if ($stablecmidnumber === '') {
        $stablecmidnumber = s5_default_stable_cmidnumber($unit);
    }
    $manifestidentifier = s5_first_string_value($sources, 'scormManifestIdentifier');
    if ($manifestidentifier === '') {
        $manifestidentifier = s5_default_manifest_identifier($unit);
    }
    $componentmappings = s5_first_array_value($sources, 'componentMappings');
    $packagepath = s5_first_string_value([$export, $item], 'zipPath');
    $packagepath = $packagepath !== '' ? $packagepath : s5_first_string_value([$export, $item], 'packagePath');

    $expected = [];
    foreach ($componentmappings as $mapping) {
        if (!is_array($mapping)) {
            continue;
        }
        $identifier = trim((string)($mapping['scoIdentifier'] ?? ''));
        if ($identifier !== '') {
            $expected[] = $identifier;
        }
    }
    $expected = array_values(array_unique($expected));

    return [
        'valid' => true,
        'status' => 'RESOLVED',
        'WorldCode' => $unit['WorldCode'],
        'DeploymentStageCode' => $unit['DeploymentStageCode'],
        'courseExternalKey' => $unit['courseExternalKey'],
        'courseIdnumber' => $unit['courseIdnumber'],
        'UnitID' => $unit['UnitID'],
        'unitNumber' => $unit['unitNumber'],
        'unitSequence' => $unit['unitSequence'],
        'unitTitle' => $unit['unitTitle'],
        'expectedSectionName' => $unit['expectedSectionName'],
        'UnitSCORMActivityID' => $activityid,
        'stableCmidNumber' => clean_short_text($stablecmidnumber, 100),
        'scormManifestIdentifier' => $manifestidentifier,
        'packagePath' => $packagepath,
        'packageSha256' => s5_first_string_value($sources, 'packageSha256'),
        'packageContentSha256' => s5_first_string_value($sources, 'packageContentSha256'),
        'componentMappings' => $componentmappings,
        'expectedScoIdentifiers' => $expected,
        'unitDefinition' => $unit,
        'target' => $target,
        'item' => $item,
    ];
}

function scorm_package_manifest_details(string $packagepath): array {
    if ($packagepath === '' || !file_exists($packagepath) || !is_file($packagepath)) {
        return [
            'valid' => false,
            'status' => 'SCORM_PACKAGE_INVALID',
            'message' => 'SCORM package ZIP was not found.',
            'packagePath' => $packagepath,
        ];
    }

    $ziparch = new zip_archive();
    if (!$ziparch->open($packagepath, file_archive::OPEN)) {
        return [
            'valid' => false,
            'status' => 'SCORM_PACKAGE_INVALID',
            'message' => 'SCORM package ZIP could not be opened.',
            'packagePath' => $packagepath,
        ];
    }

    $manifestxml = null;
    foreach ($ziparch as $info) {
        $pathname = str_replace('\\', '/', (string)$info->pathname);
        if (!$info->is_directory && strtolower($pathname) === 'imsmanifest.xml') {
            $stream = $ziparch->get_stream($info->index);
            if ($stream) {
                $manifestxml = stream_get_contents($stream);
                fclose($stream);
            }
            break;
        }
    }
    $ziparch->close();

    if (!is_string($manifestxml) || trim($manifestxml) === '') {
        return [
            'valid' => false,
            'status' => 'SCORM_PACKAGE_INVALID',
            'message' => 'SCORM package does not contain root imsmanifest.xml.',
            'packagePath' => $packagepath,
        ];
    }

    $previous = libxml_use_internal_errors(true);
    $xml = simplexml_load_string($manifestxml);
    $errors = libxml_get_errors();
    libxml_clear_errors();
    libxml_use_internal_errors($previous);
    if (!$xml) {
        return [
            'valid' => false,
            'status' => 'SCORM_PACKAGE_INVALID',
            'message' => 'imsmanifest.xml could not be parsed as XML.',
            'xmlErrors' => array_map(fn($error) => trim($error->message), $errors),
            'packagePath' => $packagepath,
        ];
    }

    $items = $xml->xpath('//*[local-name()="item"]') ?: [];
    $launchitems = [];
    foreach ($items as $node) {
        $identifier = trim((string)$node['identifier']);
        $identifierref = trim((string)$node['identifierref']);
        if ($identifier === '' || $identifierref === '') {
            continue;
        }
        $titles = $node->xpath('./*[local-name()="title"]') ?: [];
        $launchitems[] = [
            'identifier' => $identifier,
            'identifierref' => $identifierref,
            'title' => $titles ? trim((string)$titles[0]) : '',
        ];
    }
    $identifiers = array_map(fn($row) => $row['identifier'], $launchitems);
    $duplicates = array_values(array_unique(array_diff_assoc($identifiers, array_unique($identifiers))));

    return [
        'valid' => count($launchitems) > 0 && count($duplicates) === 0,
        'status' => (count($launchitems) > 0 && count($duplicates) === 0) ? 'OK' : 'SCORM_PACKAGE_INVALID',
        'message' => count($launchitems) > 0 ? '' : 'SCORM manifest does not contain launchable SCO items.',
        'packagePath' => $packagepath,
        'packageSha1' => sha1_file($packagepath),
        'packageSha256' => hash_file('sha256', $packagepath),
        'packageSize' => filesize($packagepath),
        'manifestIdentifier' => trim((string)$xml['identifier']),
        'launchScoCount' => count($launchitems),
        'launchScoIdentifiers' => $identifiers,
        'launchItems' => $launchitems,
        'duplicateScoIdentifiers' => $duplicates,
    ];
}

function validate_unit_scorm_package(array $definition, array $package): array {
    if (empty($package['valid'])) {
        return $package;
    }
    $problems = [];
    $expectedmanifest = trim((string)($definition['scormManifestIdentifier'] ?? ''));
    $actualmanifest = trim((string)($package['manifestIdentifier'] ?? ''));
    if ($expectedmanifest !== '' && $actualmanifest !== '' && $expectedmanifest !== $actualmanifest) {
        $problems[] = 'Manifest identifier mismatch: expected ' . $expectedmanifest . ', got ' . $actualmanifest . '.';
    }
    $expected = $definition['expectedScoIdentifiers'] ?? [];
    if ($expected) {
        $actual = $package['launchScoIdentifiers'] ?? [];
        $missing = array_values(array_diff($expected, $actual));
        if ($missing) {
            $problems[] = 'Manifest is missing expected SCO identifiers: ' . implode(', ', $missing) . '.';
        }
    }
    if ($problems) {
        $package['valid'] = false;
        $package['status'] = 'SCORM_PACKAGE_INVALID';
        $package['message'] = implode(' ', $problems);
    }
    return $package;
}

function scorm_module_permission(stdClass $course): array {
    $context = context_course::instance((int)$course->id);
    return [
        'canManageActivities' => has_capability('moodle/course:manageactivities', $context),
        'canAddScorm' => has_capability('mod/scorm:addinstance', $context),
        'canUpdateCourse' => has_capability('moodle/course:update', $context),
        'manageCapability' => 'moodle/course:manageactivities',
        'addCapability' => 'mod/scorm:addinstance',
        'context' => 'course:' . (int)$course->id,
    ];
}

function scorm_module_for_cmid(int $courseid, int $cmid): ?array {
    global $DB;

    $module = $DB->get_record('modules', ['name' => 'scorm'], 'id,name', MUST_EXIST);
    $cm = $DB->get_record('course_modules', ['id' => $cmid, 'course' => $courseid, 'module' => $module->id], '*', IGNORE_MISSING);
    if (!$cm || !empty($cm->deletioninprogress)) {
        return null;
    }
    $scorm = $DB->get_record('scorm', ['id' => (int)$cm->instance], '*', IGNORE_MISSING);
    if (!$scorm) {
        return null;
    }
    return ['cm' => $cm, 'scorm' => $scorm];
}

function scorm_manifest_identifiers_for_instance(int $scormid): array {
    global $DB;

    $records = $DB->get_records_select('scorm_scoes', 'scorm = :scorm AND manifest <> :empty',
        ['scorm' => $scormid, 'empty' => ''], 'manifest ASC', 'DISTINCT manifest');
    return array_values(array_map(fn($row) => (string)$row->manifest, $records));
}

function scorm_sco_identifier_rows(int $scormid): array {
    global $DB;

    $records = $DB->get_records('scorm_scoes', ['scorm' => $scormid], 'sortorder ASC, id ASC',
        'id,scorm,manifest,organization,parent,identifier,launch,scormtype,title,sortorder');
    $rows = [];
    foreach ($records as $record) {
        if ((string)($record->scormtype ?? '') !== 'sco') {
            continue;
        }
        $rows[(string)$record->identifier] = [
            'scoid' => (int)$record->id,
            'identifier' => (string)$record->identifier,
            'title' => (string)($record->title ?? ''),
            'launch' => (string)($record->launch ?? ''),
            'sortorder' => (int)($record->sortorder ?? 0),
        ];
    }
    return $rows;
}

function scorm_tracking_summary(int $scormid): array {
    global $DB;

    $attempts = $DB->count_records('scorm_attempt', ['scormid' => $scormid]);
    $sql = "SELECT s.id, s.identifier, COUNT(v.id) AS valuecount, COUNT(DISTINCT a.userid) AS usercount
              FROM {scorm_scoes} s
         LEFT JOIN {scorm_scoes_value} v ON v.scoid = s.id
         LEFT JOIN {scorm_attempt} a ON a.id = v.attemptid
             WHERE s.scorm = :scorm
          GROUP BY s.id, s.identifier
          ORDER BY s.sortorder ASC, s.id ASC";
    $rows = [];
    $tracked = [];
    foreach ($DB->get_records_sql($sql, ['scorm' => $scormid]) as $record) {
        $row = [
            'scoid' => (int)$record->id,
            'identifier' => (string)$record->identifier,
            'valueCount' => (int)$record->valuecount,
            'userCount' => (int)$record->usercount,
        ];
        $rows[] = $row;
        if ($row['valueCount'] > 0 && $row['identifier'] !== '') {
            $tracked[] = $row['identifier'];
        }
    }
    return [
        'attempts' => (int)$attempts,
        'trackedScoIdentifiers' => array_values(array_unique($tracked)),
        'scoRows' => $rows,
    ];
}

function s8_scorm_history_summary(stdClass $cm, stdClass $scorm): array {
    global $DB;

    $tracking = scorm_tracking_summary((int)$scorm->id);
    $trackingrows = array_sum(array_map(fn($row) => (int)($row['valueCount'] ?? 0), $tracking['scoRows'] ?? []));
    $manager = $DB->get_manager();
    $gradeitems = 0;
    $gradegrades = 0;
    if ($manager->table_exists('grade_items')) {
        $gradeitemrecords = $DB->get_records('grade_items', [
            'itemtype' => 'mod',
            'itemmodule' => 'scorm',
            'iteminstance' => (int)$scorm->id,
        ], 'id ASC', 'id');
        $gradeitems = count($gradeitemrecords);
        if ($gradeitems && $manager->table_exists('grade_grades')) {
            [$insql, $params] = $DB->get_in_or_equal(array_keys($gradeitemrecords), SQL_PARAMS_NAMED, 'gradeitemid');
            $gradegrades = $DB->count_records_select(
                'grade_grades',
                "itemid {$insql} AND (finalgrade IS NOT NULL OR rawgrade IS NOT NULL OR overridden > 0 OR locked > 0)",
                $params
            );
        }
    }
    $completion = $manager->table_exists('course_modules_completion')
        ? $DB->count_records('course_modules_completion', ['coursemoduleid' => (int)$cm->id])
        : 0;
    $present = ((int)$tracking['attempts'] > 0) || $trackingrows > 0 || $gradegrades > 0 || $completion > 0;
    return [
        'present' => $present,
        'attempts' => (int)$tracking['attempts'],
        'trackingRows' => (int)$trackingrows,
        'trackedScoIdentifiers' => $tracking['trackedScoIdentifiers'] ?? [],
        'gradeItems' => (int)$gradeitems,
        'gradeGrades' => (int)$gradegrades,
        'completionRows' => (int)$completion,
        'risk' => $present ? 'LEARNER_HISTORY_PRESENT' : 'NONE',
    ];
}

function s8_cmidnumber_is_importer_owned(string $cmidnumber, array $definition): bool {
    $stable = (string)($definition['stableCmidNumber'] ?? '');
    if ($stable === '' || $cmidnumber === '') {
        return false;
    }
    return $cmidnumber === $stable
        || strncmp($cmidnumber, $stable . '_REV', strlen($stable) + 4) === 0
        || strncmp($cmidnumber, $stable . '_REBUILD_PENDING_', strlen($stable) + 17) === 0;
}

function s8_section_manual_content_summary(stdClass $course, stdClass $section, array $definition): array {
    global $DB;

    $sequence = trim((string)($section->sequence ?? ''));
    if ($sequence === '') {
        return ['present' => false, 'count' => 0, 'objects' => []];
    }
    $cmids = array_values(array_filter(array_map('intval', explode(',', $sequence)), fn($id) => $id > 0));
    if (!$cmids) {
        return ['present' => false, 'count' => 0, 'objects' => []];
    }
    [$insql, $params] = $DB->get_in_or_equal($cmids, SQL_PARAMS_NAMED, 'cmid');
    $params['course'] = (int)$course->id;
    $cms = $DB->get_records_select('course_modules', "id {$insql} AND course = :course", $params, 'id ASC',
        'id,course,module,instance,idnumber,section,deletioninprogress');
    $objects = [];
    foreach ($cms as $cm) {
        if (!empty($cm->deletioninprogress)) {
            continue;
        }
        if (s8_cmidnumber_is_importer_owned((string)($cm->idnumber ?? ''), $definition)) {
            continue;
        }
        $module = $DB->get_record('modules', ['id' => (int)$cm->module], 'id,name', IGNORE_MISSING);
        $objects[] = [
            'cmid' => (int)$cm->id,
            'module' => $module ? (string)$module->name : '',
            'idnumber' => (string)($cm->idnumber ?? ''),
            'ownership' => 'MANUAL_OR_NON_FLW',
        ];
    }
    return [
        'present' => count($objects) > 0,
        'count' => count($objects),
        'objects' => $objects,
    ];
}

function scorm_current_snapshot(stdClass $cm, stdClass $scorm): array {
    global $CFG;

    $scoes = scorm_sco_identifier_rows((int)$scorm->id);
    $tracking = scorm_tracking_summary((int)$scorm->id);
    return [
        'cmid' => (int)$cm->id,
        'scormId' => (int)$scorm->id,
        'cmidnumber' => (string)($cm->idnumber ?? ''),
        'name' => (string)($scorm->name ?? ''),
        'visible' => (int)($cm->visible ?? 1),
        'section' => (int)($cm->section ?? 0),
        'reference' => (string)($scorm->reference ?? ''),
        'sha1hash' => (string)($scorm->sha1hash ?? ''),
        'revision' => (int)($scorm->revision ?? 0),
        'manifestIdentifiers' => scorm_manifest_identifiers_for_instance((int)$scorm->id),
        'scoIdentifiers' => array_keys($scoes),
        'scoRows' => array_values($scoes),
        'tracking' => $tracking,
        'viewUrl' => rtrim((string)$CFG->wwwroot, '/') . '/mod/scorm/view.php?id=' . (int)$cm->id,
    ];
}

function find_scorm_by_stable_cmidnumber(stdClass $course, string $cmidnumber): array {
    global $DB;

    $module = $DB->get_record('modules', ['name' => 'scorm'], 'id,name', MUST_EXIST);
    $records = $DB->get_records('course_modules', [
        'course' => (int)$course->id,
        'module' => (int)$module->id,
        'idnumber' => $cmidnumber,
    ], 'id ASC');
    $valid = [];
    foreach ($records as $cm) {
        if (!empty($cm->deletioninprogress)) {
            continue;
        }
        $scorm = $DB->get_record('scorm', ['id' => (int)$cm->instance], '*', IGNORE_MISSING);
        if ($scorm) {
            $valid[] = ['cm' => $cm, 'scorm' => $scorm];
        }
    }
    if (count($valid) > 1) {
        return ['status' => 'SCORM_DUPLICATE', 'matches' => $valid];
    }
    if (count($valid) === 1) {
        return ['status' => 'FOUND', 'method' => 'STABLE_CMIDNUMBER', 'match' => $valid[0]];
    }
    return ['status' => 'NOT_FOUND'];
}

function find_safe_scorm_adoption_candidate(stdClass $course, stdClass $section, array $definition): array {
    global $DB;

    $module = $DB->get_record('modules', ['name' => 'scorm'], 'id,name', MUST_EXIST);
    $sequence = trim((string)($section->sequence ?? ''));
    if ($sequence === '') {
        return ['status' => 'NOT_FOUND'];
    }
    $cmids = array_values(array_filter(array_map('intval', explode(',', $sequence)), fn($id) => $id > 0));
    if (!$cmids) {
        return ['status' => 'NOT_FOUND'];
    }
    [$insql, $params] = $DB->get_in_or_equal($cmids, SQL_PARAMS_NAMED, 'cmid');
    $params['course'] = (int)$course->id;
    $params['module'] = (int)$module->id;
    $candidates = $DB->get_records_select('course_modules',
        "id {$insql} AND course = :course AND module = :module",
        $params,
        'id ASC'
    );
    $matches = [];
    foreach ($candidates as $cm) {
        if (!empty($cm->deletioninprogress) || trim((string)$cm->idnumber) !== '') {
            continue;
        }
        $scorm = $DB->get_record('scorm', ['id' => (int)$cm->instance], '*', IGNORE_MISSING);
        if (!$scorm) {
            continue;
        }
        $manifests = scorm_manifest_identifiers_for_instance((int)$scorm->id);
        if (in_array((string)$definition['scormManifestIdentifier'], $manifests, true)) {
            $matches[] = ['cm' => $cm, 'scorm' => $scorm, 'manifestIdentifiers' => $manifests];
        }
    }
    if (count($matches) > 1) {
        return ['status' => 'SCORM_DUPLICATE', 'matches' => $matches];
    }
    if (count($matches) === 1) {
        return ['status' => 'FOUND', 'method' => 'SAFE_MANIFEST_ADOPTION', 'match' => $matches[0]];
    }
    return ['status' => 'NOT_FOUND'];
}

function resolve_current_unit_scorm(stdClass $course, stdClass $section, array $definition, string $map_path, bool $dryrun): array {
    $map = load_unit_scorm_map($map_path);
    $key = $definition['UnitSCORMActivityID'];
    $entry = $map['unitScormActivities'][$key] ?? null;
    $staleentry = null;
    if ($entry && !empty($entry['currentCmid'])) {
        $mappedcourseid = (int)($entry['moodleCourseId'] ?? 0);
        if ($mappedcourseid > 0 && $mappedcourseid !== (int)$course->id) {
            return ['status' => 'SCORM_IDENTITY_CONFLICT', 'message' => 'Unit SCORM map points to a different Moodle Course.', 'entry' => $entry];
        }
        $mappedcmid = (int)$entry['currentCmid'];
        $mapped = scorm_module_for_cmid((int)$course->id, $mappedcmid);
        if (!$mapped) {
            if (mapping_predates_recreated_course($course, $entry)) {
                $staleentry = $entry;
                $entry = null;
            } else {
                return ['status' => 'SCORM_TARGET_MISSING', 'message' => 'Unit SCORM map points to a missing or non-SCORM course module.', 'entry' => $entry];
            }
        }
        if ($mapped && (int)$mapped['cm']->section !== (int)$section->id) {
            return ['status' => 'SCORM_IDENTITY_CONFLICT', 'message' => 'Unit SCORM map points to a SCORM activity in a different Unit Section.', 'entry' => $entry, 'current' => $mapped];
        }
        if ($mapped) {
            $stable = find_scorm_by_stable_cmidnumber($course, $definition['stableCmidNumber']);
            if ($stable['status'] === 'SCORM_DUPLICATE') {
                return ['status' => 'SCORM_DUPLICATE', 'message' => 'Multiple SCORM activities use the same stable cmidnumber.', 'matches' => $stable['matches'], 'entry' => $entry];
            }
            if ($stable['status'] === 'FOUND' && (int)$stable['match']['cm']->id !== $mappedcmid) {
                return ['status' => 'SCORM_IDENTITY_CONFLICT', 'message' => 'Unit SCORM map and stable cmidnumber resolve to different Moodle activities.', 'entry' => $entry, 'current' => $mapped, 'stable' => $stable['match']];
            }
            return ['status' => 'FOUND', 'method' => 'UNIT_SCORM_MAP', 'match' => $mapped, 'entry' => $entry];
        }
    }

    $stable = find_scorm_by_stable_cmidnumber($course, $definition['stableCmidNumber']);
    if ($stable['status'] === 'SCORM_DUPLICATE') {
        return ['status' => 'SCORM_DUPLICATE', 'message' => 'Multiple SCORM activities use the same stable cmidnumber.', 'matches' => $stable['matches']];
    }
    if ($stable['status'] === 'FOUND') {
        if ((int)$stable['match']['cm']->section !== (int)$section->id) {
            return ['status' => 'SCORM_IDENTITY_CONFLICT', 'message' => 'Stable cmidnumber exists outside the resolved Unit Section.', 'current' => $stable['match']];
        }
        if ($staleentry) {
            $stable['staleEntry'] = $staleentry;
            $stable['staleMappingReason'] = 'STAGE_COURSE_RECREATED_AFTER_MAPPING';
        }
        return $stable;
    }

    $candidate = find_safe_scorm_adoption_candidate($course, $section, $definition);
    if ($candidate['status'] === 'SCORM_DUPLICATE') {
        return ['status' => 'SCORM_DUPLICATE', 'message' => 'Multiple safe FLW SCORM adoption candidates were found in the Unit Section.', 'matches' => $candidate['matches']];
    }
    if ($candidate['status'] === 'FOUND') {
        if (!$dryrun) {
            set_coursemodule_idnumber((int)$candidate['match']['cm']->id, $definition['stableCmidNumber']);
            $candidate['match'] = scorm_module_for_cmid((int)$course->id, (int)$candidate['match']['cm']->id);
        }
        return $candidate;
    }

    return [
        'status' => 'NOT_FOUND',
        'method' => 'CREATE_SCORM',
        'staleEntry' => $staleentry,
        'staleMappingReason' => $staleentry ? 'STAGE_COURSE_RECREATED_AFTER_MAPPING' : '',
    ];
}

function s5_apply_scorm_settings(stdClass $data, stdClass $course, int $sectionnum, array $definition, string $packagepath, bool $forupdate, ?stdClass $currentscorm = null, ?string $cmidnumber_override = null): stdClass {
    $cfgscorm = get_config('scorm');
    $title = clean_short_text('U' . s5_unit_number_for_identifier($definition) . ' — ' . ($definition['unitTitle'] ?: $definition['UnitID']), 255);
    $data->section = $sectionnum;
    $data->name = $title;
    $data->cmidnumber = $cmidnumber_override ?: $definition['stableCmidNumber'];
    $data->introeditor = [
        'text' => '<p>Current FLW Unit SCORM package for ' . s($definition['UnitID']) . '. Imported by Smart Course Editor S5.</p>',
        'format' => FORMAT_HTML,
        'itemid' => file_get_unused_draft_itemid(),
    ];
    $data->scormtype = SCORM_TYPE_LOCAL;
    $data->packagefile = draft_file_from_path($packagepath);
    $data->packageurl = '';
    $data->reference = basename($packagepath);
    $data->version = $currentscorm ? (string)($currentscorm->version ?? '') : '';
    $data->maxgrade = cfg_value($cfgscorm, 'maxgrade', 100);
    $data->grademethod = cfg_value($cfgscorm, 'grademethod', GRADESCOES);
    $data->whatgrade = cfg_value($cfgscorm, 'whatgrade', HIGHESTATTEMPT);
    $data->maxattempt = cfg_value($cfgscorm, 'maxattempt', 1);
    $data->forcecompleted = cfg_value($cfgscorm, 'forcecompleted', 0);
    $data->forcenewattempt = cfg_value($cfgscorm, 'forcenewattempt', SCORM_FORCEATTEMPT_NO);
    $data->lastattemptlock = cfg_value($cfgscorm, 'lastattemptlock', 0);
    $data->masteryoverride = cfg_value($cfgscorm, 'masteryoverride', 1);
    $data->displayattemptstatus = SCORM_DISPLAY_ATTEMPTSTATUS_NO;
    $data->displaycoursestructure = 0;
    $data->updatefreq = SCORM_UPDATE_NEVER;
    $data->sha1hash = $forupdate && $currentscorm ? (string)$currentscorm->sha1hash : sha1_file($packagepath);
    $data->md5hash = md5_file($packagepath);
    $data->revision = $forupdate && $currentscorm ? (int)$currentscorm->revision : 0;
    $data->launch = $forupdate && $currentscorm ? (int)$currentscorm->launch : 0;
    $data->skipview = SCORM_SKIPVIEW_ALWAYS;
    $data->hidebrowse = 1;
    $data->hidetoc = SCORM_TOC_DISABLED;
    $data->nav = SCORM_NAV_DISABLED;
    $data->navpositionleft = cfg_value($cfgscorm, 'navpositionleft', -100);
    $data->navpositiontop = cfg_value($cfgscorm, 'navpositiontop', -100);
    $data->auto = cfg_value($cfgscorm, 'auto', 0);
    $data->popup = 0;
    $data->options = '';
    $data->width = cfg_value($cfgscorm, 'framewidth', 100);
    $data->height = cfg_value($cfgscorm, 'frameheight', 600);
    $data->timeopen = 0;
    $data->timeclose = 0;
    $data->timemodified = time();
    $data->completionstatusrequired = null;
    $data->completionscorerequired = null;
    $data->completionstatusallscos = 0;
    $data->autocommit = cfg_value($cfgscorm, 'autocommit', 0);
    $data->tags = [];
    return $data;
}

function build_unit_scorm_moduleinfo(stdClass $course, int $sectionnum, array $definition, string $packagepath, ?string $cmidnumber_override = null): stdClass {
    [, , , , $data] = prepare_new_moduleinfo_data($course, 'scorm', $sectionnum);
    return s5_apply_scorm_settings($data, $course, $sectionnum, $definition, $packagepath, false, null, $cmidnumber_override);
}

function build_unit_scorm_updateinfo(stdClass $course, stdClass $cm, stdClass $scorm, int $sectionnum, array $definition, string $packagepath): stdClass {
    [, , , $data] = get_moduleinfo_data($cm, $course);
    return s5_apply_scorm_settings($data, $course, $sectionnum, $definition, $packagepath, true, $scorm);
}

function scorm_update_safety(stdClass $scorm, array $newidentifiers): array {
    $tracking = scorm_tracking_summary((int)$scorm->id);
    $tracked = $tracking['trackedScoIdentifiers'];
    $missingtracked = array_values(array_diff($tracked, $newidentifiers));
    if ($missingtracked) {
        return [
            'safe' => false,
            'status' => 'SCORM_UPDATE_UNSAFE',
            'historyRisk' => 'TRACKED_SCO_IDENTIFIER_REMOVED',
            'attemptsPresent' => $tracking['attempts'] > 0,
            'missingTrackedScoIdentifiers' => $missingtracked,
            'tracking' => $tracking,
        ];
    }
    return [
        'safe' => true,
        'status' => $tracking['attempts'] > 0 ? 'SCORM_ATTEMPTS_PRESENT' : 'SAFE_NO_ATTEMPTS',
        'historyRisk' => $tracking['attempts'] > 0 ? 'TRACKING_PRESENT_BUT_IDENTIFIERS_STABLE' : 'NONE',
        'attemptsPresent' => $tracking['attempts'] > 0,
        'missingTrackedScoIdentifiers' => [],
        'tracking' => $tracking,
    ];
}

function record_unit_scorm_mapping(array $definition, stdClass $course, stdClass $section, stdClass $cm, stdClass $scorm, string $status, string $map_path, array $package, array $extra = []): void {
    $map = load_unit_scorm_map($map_path);
    $key = $definition['UnitSCORMActivityID'];
    $existing = $map['unitScormActivities'][$key] ?? [];
    if (!empty($extra['replaceStaleMapping'])) {
        $existing = [];
    }
    $now = date('c');
    $history = $existing['history'] ?? [];
    if (!empty($extra['appendHistory']) && is_array($extra['appendHistory'])) {
        $history[] = $extra['appendHistory'];
    }
    $previousrevision = (int)($existing['currentRevision'] ?? 0);
    $currentrevision = (int)($extra['currentRevision'] ?? max($previousrevision, (int)($scorm->revision ?? 0), 1));
    if (in_array($status, ['CREATE_SCORM', 'UPDATE_SCORM', 'SUPERSEDE_SCORM'], true)) {
        $currentrevision = max(1, $previousrevision + (($status === 'CREATE_SCORM' && $previousrevision === 0) ? 1 : 1));
    } else if ($currentrevision <= 0) {
        $currentrevision = 1;
    }
    $map['unitScormActivities'][$key] = [
        'UnitID' => $definition['UnitID'],
        'UnitSCORMActivityID' => $definition['UnitSCORMActivityID'],
        'WorldCode' => $definition['WorldCode'],
        'DeploymentStageCode' => $definition['DeploymentStageCode'],
        'courseExternalKey' => $definition['courseExternalKey'],
        'moodleCourseId' => (int)$course->id,
        'moodleSectionId' => (int)$section->id,
        'moodleSectionNumber' => (int)$section->section,
        'stableCmidNumber' => $definition['stableCmidNumber'],
        'scormManifestIdentifier' => $definition['scormManifestIdentifier'],
        'currentRevision' => $currentrevision,
        'currentCmid' => (int)$cm->id,
        'currentScormId' => (int)$scorm->id,
        'packageSha1' => $package['packageSha1'] ?? '',
        'packageSha256' => $package['packageSha256'] ?? '',
        'packageContentSha256' => $definition['packageContentSha256'] ?? '',
        'componentScoIdentifiers' => $package['launchScoIdentifiers'] ?? [],
        'status' => 'CURRENT',
        'lastAction' => $status,
        'createdAt' => $existing['createdAt'] ?? $now,
        'updatedAt' => $now,
        'history' => $history,
    ];
    save_unit_scorm_map($map_path, $map);
}

function summarize_scorm_result_for_report(array $result): array {
    return [
        'scormAction' => $result['scormAction'] ?? '',
        'scormStatus' => $result['scormStatus'] ?? ($result['scormAction'] ?? ''),
        'cmid' => $result['cmid'] ?? null,
        'scormId' => $result['scormId'] ?? null,
        'stableCmidNumber' => $result['stableCmidNumber'] ?? '',
        'currentPackageSha256' => $result['currentPackageSha256'] ?? '',
        'newPackageSha256' => $result['newPackageSha256'] ?? '',
        'historyRisk' => $result['historyRisk'] ?? '',
        'resolutionMethod' => $result['scormResolutionMethod'] ?? '',
    ];
}

function retire_current_scorm_for_supersession(stdClass $course, stdClass $cm, stdClass $scorm, array $definition, int $revision, array $existingentry = []): array {
    $oldidnumber = (string)($cm->idnumber ?? '');
    $retiredidnumber = clean_short_text($definition['stableCmidNumber'] . '_REV' . max(1, $revision) . '_SUPERSEDED', 100);
    if ($oldidnumber === $retiredidnumber) {
        $retiredidnumber = clean_short_text($definition['stableCmidNumber'] . '_REV' . max(1, $revision) . '_' . date('YmdHis'), 100);
    }
    set_coursemodule_idnumber((int)$cm->id, $retiredidnumber);
    set_coursemodule_visible((int)$cm->id, 0, 0);
    set_coursemodule_name((int)$cm->id, clean_short_text('[Superseded] ' . (string)($scorm->name ?? $definition['UnitID']), 255));
    rebuild_course_cache((int)$course->id, true);
    return [
        'cmid' => (int)$cm->id,
        'scormId' => (int)$scorm->id,
        'deploymentRevision' => max(1, $revision),
        'oldCmidNumber' => $oldidnumber,
        'retiredCmidNumber' => $retiredidnumber,
        'retiredVisible' => 0,
        'packageSha1' => (string)($scorm->sha1hash ?? ''),
        'packageSha256' => (string)($existingentry['packageSha256'] ?? ''),
        'packageContentSha256' => (string)($existingentry['packageContentSha256'] ?? ''),
        'componentScoIdentifiers' => is_array($existingentry['componentScoIdentifiers'] ?? null) ? $existingentry['componentScoIdentifiers'] : [],
        'tracking' => scorm_tracking_summary((int)$scorm->id),
        'retiredAt' => date('c'),
    ];
}

function deploy_unit_scorm_activity(array $item, array $stage_resolution, array $section_result, bool $dryrun, string $map_path, bool $force_supersede = false, bool $safe_rebuild = false): array {
    global $DB, $CFG;

    $definition = unit_scorm_definition($item);
    $legacycount = count(array_filter($stage_resolution['potentialConflicts'] ?? [], fn($conflict) => ($conflict['status'] ?? '') === 'LEGACY_UNIT_COURSE_FOUND'));
    $base = [
        'scormAction' => 'SCORM_PENDING_S5',
        'scormStatus' => 'SCORM_PENDING_S5',
        'scormActivitiesImported' => 0,
        'unitScormActivityId' => $definition['UnitSCORMActivityID'] ?? '',
        'stableCmidNumber' => $definition['stableCmidNumber'] ?? '',
        'scormManifestIdentifier' => $definition['scormManifestIdentifier'] ?? '',
        'unitScormMapPath' => $map_path,
        's8RebuildMode' => $safe_rebuild,
        'legacyUnitCoursePresent' => $legacycount > 0,
        'legacyUnitCourseCount' => $legacycount,
        'legacyUnitCourseResult' => $legacycount > 0 ? 'LEGACY_UNIT_COURSE_PRESENT' : 'NONE',
    ];
    if (empty($definition['valid'])) {
        return array_merge($base, [
            'scormAction' => 'COURSE_NOT_RESOLVED',
            'scormStatus' => 'COURSE_NOT_RESOLVED',
            'message' => $definition['message'] ?? 'Unit SCORM definition is invalid.',
        ]);
    }
    if ($dryrun && empty($section_result['sectionId']) && (($section_result['status'] ?? '') === 'CREATE_SECTION')) {
        return array_merge($base, [
            'scormAction' => 'CREATE_SCORM',
            'scormStatus' => 'CREATE_SCORM',
            'currentCmid' => null,
            'currentScormId' => null,
            'currentPackageSha256' => '',
            'historyRisk' => 'NONE',
            'scormResolutionMethod' => 'CREATE_SCORM',
            'message' => 'Unit SCORM activity would be created after the new Unit Section is created.',
        ]);
    }
    if (empty($section_result['sectionId']) || in_array(($section_result['status'] ?? ''), [
        'COURSE_NOT_RESOLVED',
        'UNIT_ALREADY_EXISTS',
        'UNIT_SECTION_DUPLICATE',
        'UNIT_SECTION_TARGET_MISSING',
        'UNIT_STAGE_MOVE_REQUIRED',
        'SECTION_MAPPING_CONFLICT',
        'PERMISSION_DENIED',
        'SECTION_CREATE_FAILED',
        'SECTION_UPDATE_FAILED',
    ], true)) {
        return array_merge($base, [
            'scormAction' => 'SECTION_NOT_RESOLVED',
            'scormStatus' => 'SECTION_NOT_RESOLVED',
            'message' => 'Unit Section must be resolved before creating or updating Unit SCORM.',
        ]);
    }
    $courseid = (int)($section_result['courseId'] ?? 0);
    $sectionid = (int)($section_result['sectionId'] ?? 0);
    $course = $courseid > 0 ? $DB->get_record('course', ['id' => $courseid], '*', IGNORE_MISSING) : false;
    $section = $sectionid > 0 ? $DB->get_record('course_sections', ['id' => $sectionid], 'id,course,section,name,summary,sequence,visible', IGNORE_MISSING) : false;
    if (!$course || !$section || (int)$section->course !== (int)$course->id) {
        return array_merge($base, [
            'scormAction' => 'SECTION_NOT_RESOLVED',
            'scormStatus' => 'SECTION_NOT_RESOLVED',
            'message' => 'Resolved Unit Section could not be found in Moodle.',
        ]);
    }
    $manualcontent = s8_section_manual_content_summary($course, $section, $definition);
    $base['manualContent'] = $manualcontent;
    $base['manualContentPresent'] = !empty($manualcontent['present']);
    $base['manualContentResult'] = !empty($manualcontent['present']) ? 'MANUAL_CONTENT_PRESENT' : 'NONE';

    $package = validate_unit_scorm_package($definition, scorm_package_manifest_details($definition['packagePath']));
    $base['newPackageSha256'] = $package['packageSha256'] ?? '';
    $base['newPackageSha1'] = $package['packageSha1'] ?? '';
    $base['manifestScoCount'] = $package['launchScoCount'] ?? null;
    $base['manifestScoIdentifiers'] = $package['launchScoIdentifiers'] ?? [];
    if (empty($package['valid'])) {
        return array_merge($base, [
            'scormAction' => 'SCORM_PACKAGE_INVALID',
            'scormStatus' => 'SCORM_PACKAGE_INVALID',
            'message' => $package['message'] ?? 'SCORM package is invalid.',
            'package' => $package,
        ]);
    }

    $permission = scorm_module_permission($course);
    $base['permission'] = $permission;
    if (!$dryrun && (empty($permission['canManageActivities']) || empty($permission['canAddScorm']))) {
        return array_merge($base, [
            'scormAction' => 'PERMISSION_DENIED',
            'scormStatus' => 'PERMISSION_DENIED',
            'message' => 'Current Moodle user cannot add/update SCORM activities in this Stage Course.',
        ]);
    }

    $resolved = resolve_current_unit_scorm($course, $section, $definition, $map_path, $dryrun);
    if (in_array(($resolved['status'] ?? ''), ['SCORM_TARGET_MISSING', 'SCORM_DUPLICATE', 'SCORM_IDENTITY_CONFLICT'], true)) {
        return array_merge($base, [
            'scormAction' => $resolved['status'],
            'scormStatus' => $resolved['status'],
            'message' => $resolved['message'] ?? 'Unit SCORM target could not be safely resolved.',
            'resolution' => $resolved,
        ]);
    }
    $stalescormmapping = !empty($resolved['staleEntry']);
    $base['staleScormMappingRecovered'] = $stalescormmapping;
    if ($stalescormmapping) {
        $base['staleScormMappingReason'] = $resolved['staleMappingReason'] ?? 'STAGE_COURSE_RECREATED_AFTER_MAPPING';
        $base['previousMappedCmid'] = (int)($resolved['staleEntry']['currentCmid'] ?? 0);
    }

    if (($resolved['status'] ?? '') !== 'FOUND') {
        if ($dryrun) {
            return array_merge($base, [
                'scormAction' => 'CREATE_SCORM',
                'scormStatus' => 'CREATE_SCORM',
                'currentCmid' => null,
                'currentScormId' => null,
                'currentPackageSha256' => '',
                'historyRisk' => 'NONE',
                'scormResolutionMethod' => 'CREATE_SCORM',
                'message' => 'Unit SCORM activity would be created in the resolved Unit Section.',
            ]);
        }
        try {
            $seedstats = seed_zip_contents_in_filepool($definition['packagePath']);
            $moduleinfo = build_unit_scorm_moduleinfo($course, (int)$section->section, $definition, $definition['packagePath']);
            $created = add_moduleinfo($moduleinfo, $course);
            rebuild_course_cache((int)$course->id, true);
            $current = scorm_module_for_cmid((int)$course->id, (int)$created->coursemodule);
            if (!$current) {
                throw new RuntimeException('Created SCORM course module could not be reloaded.');
            }
            record_unit_scorm_mapping($definition, $course, $section, $current['cm'], $current['scorm'], 'CREATE_SCORM', $map_path, $package, [
                'replaceStaleMapping' => $stalescormmapping,
            ]);
            return array_merge($base, [
                'scormAction' => 'CREATE_SCORM',
                'scormStatus' => 'CREATE_SCORM',
                'scormActivitiesImported' => 1,
                'cmid' => (int)$current['cm']->id,
                'scormId' => (int)$current['scorm']->id,
                'currentCmid' => (int)$current['cm']->id,
                'currentScormId' => (int)$current['scorm']->id,
                'currentPackageSha256' => $package['packageSha256'] ?? '',
                'historyRisk' => 'NONE',
                'scormResolutionMethod' => 'CREATE_SCORM',
                'filePoolSeed' => $seedstats,
                'current' => scorm_current_snapshot($current['cm'], $current['scorm']),
                'viewUrl' => rtrim((string)$CFG->wwwroot, '/') . '/mod/scorm/view.php?id=' . (int)$current['cm']->id,
                'message' => 'Unit SCORM activity created.',
            ]);
        } catch (Throwable $e) {
            if ($DB->is_transaction_started()) {
                $DB->force_transaction_rollback();
            }
            return array_merge($base, [
                'scormAction' => 'SCORM_CREATE_FAILED',
                'scormStatus' => 'SCORM_CREATE_FAILED',
                'message' => $e->getMessage(),
                'class' => get_class($e),
            ]);
        }
    }

    $cm = $resolved['match']['cm'];
    $scorm = $resolved['match']['scorm'];
    $current = scorm_current_snapshot($cm, $scorm);
    $history = s8_scorm_history_summary($cm, $scorm);
    $mappedcontenthash = (string)($resolved['entry']['packageContentSha256'] ?? '');
    $newcontenthash = (string)($definition['packageContentSha256'] ?? '');
    $samepackage = (!empty($current['sha1hash']) && $current['sha1hash'] === ($package['packageSha1'] ?? '')) ||
        ($mappedcontenthash !== '' && $newcontenthash !== '' && $mappedcontenthash === $newcontenthash);
    $safety = scorm_update_safety($scorm, $package['launchScoIdentifiers'] ?? []);
    $base = array_merge($base, [
        'currentCmid' => (int)$cm->id,
        'currentScormId' => (int)$scorm->id,
        'cmid' => (int)$cm->id,
        'scormId' => (int)$scorm->id,
        'currentPackageSha1' => $current['sha1hash'],
        'currentPackageSha256' => '',
        'currentRevision' => $current['revision'],
        'currentManifestIdentifiers' => $current['manifestIdentifiers'],
        'currentScoIdentifiers' => $current['scoIdentifiers'],
        'tracking' => $safety['tracking'],
        'learnerHistory' => $history,
        'learnerHistoryPresent' => !empty($history['present']),
        'historyRisk' => $safety['historyRisk'],
        'scormResolutionMethod' => $resolved['method'] ?? 'UNKNOWN',
        'current' => $current,
        'viewUrl' => $current['viewUrl'],
    ]);

    if ($samepackage && !$force_supersede) {
        if (!$dryrun) {
            record_unit_scorm_mapping($definition, $course, $section, $cm, $scorm, 'UNCHANGED', $map_path, $package, [
                'currentRevision' => max(1, (int)($resolved['entry']['currentRevision'] ?? 1)),
                'replaceStaleMapping' => $stalescormmapping,
            ]);
        }
        return array_merge($base, [
            'scormAction' => 'UNCHANGED',
            'scormStatus' => 'UNCHANGED',
            'message' => 'Current Unit SCORM already uses the requested package.',
        ]);
    }

    $mustsupersede = $force_supersede || empty($safety['safe']) || ($safe_rebuild && !empty($history['present']));
    if ($mustsupersede) {
        if ($dryrun) {
            return array_merge($base, [
                'scormAction' => 'SUPERSEDE_SCORM',
                'scormStatus' => empty($safety['safe']) ? 'SCORM_UPDATE_UNSAFE' : 'SUPERSEDE_SCORM',
                'message' => $force_supersede
                    ? 'Unit SCORM would be superseded by request; existing cmid/tracking would be preserved hidden.'
                    : ($safe_rebuild && !empty($history['present'])
                        ? 'History-bearing Unit SCORM would be superseded for safe rebuild; existing attempts/grades/completion remain with the historical activity.'
                        : 'Package removes tracked SCO identifiers; existing cmid/tracking would be preserved by supersession.'),
                'safety' => $safety,
            ]);
        }
        $createdcmid = 0;
        $pendingidnumber = clean_short_text($definition['stableCmidNumber'] . '_REBUILD_PENDING_' . date('YmdHis') . '_' . random_int(1000, 9999), 100);
        try {
            $map = load_unit_scorm_map($map_path);
            $entry = $map['unitScormActivities'][$definition['UnitSCORMActivityID']] ?? [];
            $previousrevision = (int)($entry['currentRevision'] ?? max(1, (int)$scorm->revision));
            $seedstats = seed_zip_contents_in_filepool($definition['packagePath']);
            $moduleinfo = build_unit_scorm_moduleinfo($course, (int)$section->section, $definition, $definition['packagePath'], $pendingidnumber);
            $created = add_moduleinfo($moduleinfo, $course);
            $createdcmid = (int)$created->coursemodule;
            rebuild_course_cache((int)$course->id, true);
            $newcurrent = scorm_module_for_cmid((int)$course->id, $createdcmid);
            if (!$newcurrent) {
                throw new RuntimeException('Superseding SCORM course module could not be reloaded.');
            }
            $supersededhistory = retire_current_scorm_for_supersession($course, $cm, $scorm, $definition, $previousrevision, $entry);
            set_coursemodule_idnumber($createdcmid, $definition['stableCmidNumber']);
            set_coursemodule_name($createdcmid, $moduleinfo->name);
            rebuild_course_cache((int)$course->id, true);
            $newcurrent = scorm_module_for_cmid((int)$course->id, $createdcmid);
            if (!$newcurrent) {
                throw new RuntimeException('Current superseding SCORM could not be reloaded after stable idnumber assignment.');
            }
            record_unit_scorm_mapping($definition, $course, $section, $newcurrent['cm'], $newcurrent['scorm'], 'SUPERSEDE_SCORM', $map_path, $package, [
                'appendHistory' => $supersededhistory,
                'currentRevision' => $previousrevision + 1,
                'replaceStaleMapping' => $stalescormmapping,
            ]);
            return array_merge($base, [
                'scormAction' => 'SUPERSEDE_SCORM',
                'scormStatus' => empty($safety['safe']) ? 'SCORM_UPDATE_UNSAFE' : 'SUPERSEDE_SCORM',
                'scormActivitiesImported' => 1,
                'superseded' => $supersededhistory,
                'cmid' => (int)$newcurrent['cm']->id,
                'scormId' => (int)$newcurrent['scorm']->id,
                'currentCmid' => (int)$newcurrent['cm']->id,
                'currentScormId' => (int)$newcurrent['scorm']->id,
                'currentPackageSha256' => $package['packageSha256'] ?? '',
                'current' => scorm_current_snapshot($newcurrent['cm'], $newcurrent['scorm']),
                'filePoolSeed' => $seedstats,
                'viewUrl' => rtrim((string)$CFG->wwwroot, '/') . '/mod/scorm/view.php?id=' . (int)$newcurrent['cm']->id,
                'safety' => $safety,
                'message' => 'Unit SCORM superseded; previous cmid/tracking preserved hidden.',
            ]);
        } catch (Throwable $e) {
            if ($DB->is_transaction_started()) {
                $DB->force_transaction_rollback();
            }
            if ($createdcmid > 0) {
                try {
                    set_coursemodule_visible($createdcmid, 0, 0);
                    set_coursemodule_idnumber($createdcmid, clean_short_text($pendingidnumber . '_FAILED', 100));
                    rebuild_course_cache((int)$course->id, true);
                } catch (Throwable $cleanup) {
                    // Preserve the original failure; cleanup is best-effort only.
                }
            }
            return array_merge($base, [
                'scormAction' => 'SCORM_SUPERSEDE_FAILED',
                'scormStatus' => 'SCORM_SUPERSEDE_FAILED',
                'message' => $e->getMessage(),
                'class' => get_class($e),
                'safety' => $safety,
                'failureRecovery' => $createdcmid > 0
                    ? 'Replacement creation reached Moodle but supersession did not complete; old history-bearing SCORM was not deleted and reconciliation may be required.'
                    : 'Replacement creation failed before the old current SCORM was retired; old current SCORM remains current.',
            ]);
        }
    }

    if ($dryrun) {
        return array_merge($base, [
            'scormAction' => 'UPDATE_SCORM',
            'scormStatus' => $safety['status'],
            'message' => 'Unit SCORM package would be updated in-place; stable tracked SCO identifiers are preserved.',
            'safety' => $safety,
        ]);
    }
    $failurephase = 'FILEPOOL_SEED_CONTENTS';
    try {
        $seedstats = seed_zip_contents_in_filepool($definition['packagePath']);
        $failurephase = 'BUILD_SCORM_UPDATE_INFO';
        $moduleinfo = build_unit_scorm_updateinfo($course, $cm, $scorm, (int)$section->section, $definition, $definition['packagePath']);
        $failurephase = 'SCORM_UPDATE_INSTANCE';
        if (!scorm_update_instance($moduleinfo, null)) {
            throw new RuntimeException('Moodle scorm_update_instance() returned false.');
        }
        $failurephase = 'FINALIZE_SCORM_UPDATE';
        set_coursemodule_idnumber((int)$cm->id, $definition['stableCmidNumber']);
        set_coursemodule_name((int)$cm->id, $moduleinfo->name);
        rebuild_course_cache((int)$course->id, true);
        $updated = scorm_module_for_cmid((int)$course->id, (int)$cm->id);
        if (!$updated) {
            throw new RuntimeException('Updated SCORM course module could not be reloaded.');
        }
        record_unit_scorm_mapping($definition, $course, $section, $updated['cm'], $updated['scorm'], 'UPDATE_SCORM', $map_path, $package, [
            'replaceStaleMapping' => $stalescormmapping,
        ]);
        return array_merge($base, [
            'scormAction' => 'UPDATE_SCORM',
            'scormStatus' => $safety['status'],
            'scormActivitiesImported' => 1,
            'currentPackageSha256' => $package['packageSha256'] ?? '',
            'current' => scorm_current_snapshot($updated['cm'], $updated['scorm']),
            'filePoolSeed' => $seedstats,
            'safety' => $safety,
            'message' => 'Unit SCORM package updated in-place; cmid preserved.',
        ]);
    } catch (Throwable $e) {
        if ($DB->is_transaction_started()) {
            $DB->force_transaction_rollback();
        }
        return array_merge($base, [
            'scormAction' => 'SCORM_UPDATE_FAILED',
            'scormStatus' => 'SCORM_UPDATE_FAILED',
            'message' => $e->getMessage(),
            'class' => get_class($e),
            'failurePhase' => $failurephase,
            'failureTrace' => substr($e->getTraceAsString(), 0, 8000),
            'safety' => $safety,
        ]);
    }
}

function scorm_rows_have_blockers(array $unitresults): bool {
    $blocking = [
        'SCORM_TARGET_MISSING',
        'UNIT_ALREADY_EXISTS',
        'SCORM_DUPLICATE',
        'SCORM_IDENTITY_CONFLICT',
        'SCORM_PACKAGE_INVALID',
        'SCORM_UPDATE_UNSAFE',
        'SCORM_TRACKING_MISMATCH',
        'SECTION_NOT_RESOLVED',
        'COURSE_NOT_RESOLVED',
        'PERMISSION_DENIED',
        'SCORM_CREATE_FAILED',
        'SCORM_UPDATE_FAILED',
        'SCORM_SUPERSEDE_FAILED',
    ];
    foreach ($unitresults as $row) {
        if (in_array(($row['scormAction'] ?? ''), $blocking, true) &&
            ($row['scormAction'] ?? '') !== 'SCORM_UPDATE_UNSAFE') {
            return true;
        }
    }
    return false;
}

function scorm_filepool_failure_is_retryable(array $result): bool {
    return ($result['scormAction'] ?? '') === 'SCORM_UPDATE_FAILED' &&
        ($result['class'] ?? '') === 'file_exception' &&
        str_contains(
            (string)($result['message'] ?? ''),
            'Cannot create local file pool file'
        );
}

function unit_scorm_summary_counts(array $unitresults): array {
    $counts = [];
    foreach ($unitresults as $row) {
        $status = $row['scormAction'] ?? 'UNKNOWN';
        $counts[$status] = ($counts[$status] ?? 0) + 1;
    }
    $failurestatuses = [
        'SCORM_TARGET_MISSING',
        'SCORM_DUPLICATE',
        'SCORM_IDENTITY_CONFLICT',
        'SCORM_PACKAGE_INVALID',
        'SCORM_TRACKING_MISMATCH',
        'SECTION_NOT_RESOLVED',
        'COURSE_NOT_RESOLVED',
        'PERMISSION_DENIED',
        'SCORM_CREATE_FAILED',
        'SCORM_UPDATE_FAILED',
        'SCORM_SUPERSEDE_FAILED',
    ];
    return [
        'scormStatusCounts' => $counts,
        'scormCreated' => $counts['CREATE_SCORM'] ?? 0,
        'scormUpdated' => $counts['UPDATE_SCORM'] ?? 0,
        'scormUnchanged' => $counts['UNCHANGED'] ?? 0,
        'scormSuperseded' => $counts['SUPERSEDE_SCORM'] ?? 0,
        'scormDiffRequiresPackage' => $counts['SCORM_DIFF_REQUIRES_PACKAGE'] ?? 0,
        'scormFailures' => array_sum(array_intersect_key($counts, array_flip($failurestatuses))),
        'scormActivitiesImported' => ($counts['CREATE_SCORM'] ?? 0) + ($counts['UPDATE_SCORM'] ?? 0) + ($counts['SUPERSEDE_SCORM'] ?? 0),
        'scormPendingS5' => 0,
    ];
}

function unit_section_summary(array $stage_results, array $unit_results, array $order_moves): array {
    $stage = stage_course_summary($stage_results);
    $counts = [];
    foreach ($unit_results as $row) {
        $status = $row['status'] ?? 'UNKNOWN';
        $counts[$status] = ($counts[$status] ?? 0) + 1;
    }
    $movefailures = count(array_filter($order_moves, fn($row) => in_array(($row['status'] ?? ''), ['PERMISSION_DENIED', 'SECTION_REORDER_FAILED'], true)));
    $blocking = [
        'COURSE_NOT_RESOLVED',
        'UNIT_ALREADY_EXISTS',
        'UNIT_SECTION_DUPLICATE',
        'UNIT_SECTION_TARGET_MISSING',
        'UNIT_STAGE_MOVE_REQUIRED',
        'SECTION_MAPPING_CONFLICT',
        'PERMISSION_DENIED',
        'SECTION_CREATE_FAILED',
        'SECTION_UPDATE_FAILED',
        'SECTION_REORDER_FAILED',
    ];
    return array_merge($stage, [
        'unitSectionCount' => count($unit_results),
        'reusedUnitSections' => $counts['REUSE_SECTION'] ?? 0,
        'createdUnitSections' => count(array_filter($unit_results, fn($row) => ($row['status'] ?? '') === 'CREATE_SECTION' && !empty($row['sectionId']))),
        'wouldCreateUnitSections' => count(array_filter($unit_results, fn($row) => ($row['status'] ?? '') === 'CREATE_SECTION' && empty($row['sectionId']))),
        'updatedUnitSections' => $counts['UPDATE_SECTION'] ?? 0,
        'reorderedUnitSections' => count(array_filter($order_moves, fn($row) => ($row['status'] ?? '') === 'REORDER_SECTION')),
        'unitSectionDuplicates' => $counts['UNIT_SECTION_DUPLICATE'] ?? 0,
        'unitSectionTargetMissing' => $counts['UNIT_SECTION_TARGET_MISSING'] ?? 0,
        'wrongStageUnits' => $counts['UNIT_STAGE_MOVE_REQUIRED'] ?? 0,
        'sectionMappingConflicts' => $counts['SECTION_MAPPING_CONFLICT'] ?? 0,
        'unitSectionStatusCounts' => $counts,
        'unitSectionFailures' => array_sum(array_intersect_key($counts, array_flip($blocking))) + $movefailures,
        'unitSectionsCreated' => count(array_filter($unit_results, fn($row) => ($row['status'] ?? '') === 'CREATE_SECTION' && !empty($row['sectionId']))),
        'scormActivitiesImported' => 0,
        'scormPendingS5' => count($unit_results),
    ]);
}

function s6_is_single_direct_import(array $manifest, array $items): bool {
    return (($manifest['kind'] ?? '') === 'smartcourses_scorm_direct') && count($items) === 1;
}

function s7_is_batch_manifest(array $manifest): bool {
    return in_array(($manifest['kind'] ?? ''), [
        'smartcourses_scorm_batch',
        'smartcourses_scorm_batch_job',
        'smartcourses_scorm_batch_preview',
    ], true);
}

function s7_is_batch_mapping_preview(array $manifest): bool {
    return ($manifest['kind'] ?? '') === 'smartcourses_scorm_batch_preview';
}

function s7_enforces_unique_unit_for_add_new(array $manifest, array $items, string $importmode): bool {
    return $importmode === 'add_new' && (s6_is_single_direct_import($manifest, $items) || s7_is_batch_manifest($manifest));
}

function s7_item_has_package_path(array $item): bool {
    $export = (isset($item['export']) && is_array($item['export'])) ? $item['export'] : [];
    $path = s5_first_string_value([$export, $item], 'zipPath');
    $path = $path !== '' ? $path : s5_first_string_value([$export, $item], 'packagePath');
    return $path !== '';
}

function s7_scorm_diff_requires_package_result(array $item, array $unitrow): array {
    $definition = unit_scorm_definition($item);
    return array_merge($unitrow, [
        'scormAction' => 'SCORM_DIFF_REQUIRES_PACKAGE',
        'scormStatus' => 'SCORM_DIFF_REQUIRES_PACKAGE',
        'scormActivitiesImported' => 0,
        'unitScormActivityId' => $definition['UnitSCORMActivityID'] ?? '',
        'stableCmidNumber' => $definition['stableCmidNumber'] ?? '',
        'scormManifestIdentifier' => $definition['scormManifestIdentifier'] ?? '',
        'message' => 'Mapping preview resolved the Course and Unit Section. Run Batch Deploy with Dry run only to export the package and calculate CREATE/UPDATE/UNCHANGED/SUPERSEDE SCORM action.',
    ]);
}

function s7_unit_result_status(array $row): string {
    $section = (string)($row['sectionAction'] ?? $row['status'] ?? '');
    $scorm = (string)($row['scormAction'] ?? '');
    $conflicts = [
        'UNIT_ALREADY_EXISTS',
        'UNIT_SECTION_DUPLICATE',
        'SECTION_MAPPING_CONFLICT',
        'SCORM_DUPLICATE',
        'SCORM_IDENTITY_CONFLICT',
        'COURSE_IDNUMBER_CONFLICT',
    ];
    $blocked = [
        'COURSE_NOT_RESOLVED',
        'STAGE_UNRESOLVED',
        'STAGE_CONFLICT',
        'CATEGORY_MISSING',
        'UNIT_SECTION_TARGET_MISSING',
        'UNIT_STAGE_MOVE_REQUIRED',
        'SECTION_NOT_RESOLVED',
        'PERMISSION_DENIED',
        'PREVIEW_STALE',
    ];
    $failed = [
        'SECTION_CREATE_FAILED',
        'SECTION_UPDATE_FAILED',
        'SECTION_REORDER_FAILED',
        'SCORM_PACKAGE_INVALID',
        'SCORM_TRACKING_MISMATCH',
        'SCORM_CREATE_FAILED',
        'SCORM_UPDATE_FAILED',
        'SCORM_SUPERSEDE_FAILED',
        'COURSE_CREATE_FAILED',
    ];
    if (in_array($section, $conflicts, true) || in_array($scorm, $conflicts, true)) {
        return 'CONFLICT';
    }
    if (in_array($section, $blocked, true) || in_array($scorm, $blocked, true)) {
        return 'BLOCKED';
    }
    if (in_array($section, $failed, true) || in_array($scorm, $failed, true)) {
        return 'FAILED';
    }
    if ($scorm === 'SUPERSEDE_SCORM') {
        return 'SUPERSEDED';
    }
    if ($scorm === 'UPDATE_SCORM' || $section === 'UPDATE_SECTION' || $section === 'REORDER_SECTION') {
        return 'UPDATED';
    }
    if ($scorm === 'CREATE_SCORM' || $section === 'CREATE_SECTION') {
        return 'CREATED';
    }
    if ($scorm === 'UNCHANGED' || $section === 'REUSE_SECTION') {
        return 'UNCHANGED';
    }
    if ($scorm === 'SCORM_DIFF_REQUIRES_PACKAGE' || $scorm === 'SCORM_PENDING_S5') {
        return 'PENDING';
    }
    return 'PENDING';
}

function s8_is_rebuild_mode(string $importmode): bool {
    return $importmode === 'clear_add';
}

function s8_blocked_rebuild_classification(string $status): string {
    if ($status === 'PERMISSION_DENIED') {
        return 'BLOCKED_PERMISSION';
    }
    if ($status === 'UNIT_STAGE_MOVE_REQUIRED') {
        return 'BLOCKED_STAGE_CONFLICT';
    }
    if (in_array($status, ['SCORM_DUPLICATE', 'SCORM_IDENTITY_CONFLICT', 'SECTION_MAPPING_CONFLICT', 'UNIT_SECTION_DUPLICATE', 'COURSE_IDNUMBER_CONFLICT'], true)) {
        return 'BLOCKED_MAPPING_CONFLICT';
    }
    if (in_array($status, ['STAGE_UNRESOLVED', 'STAGE_CONFLICT', 'CATEGORY_MISSING', 'COURSE_NOT_RESOLVED', 'SECTION_NOT_RESOLVED', 'SCORM_DIFF_REQUIRES_PACKAGE'], true)) {
        return 'BLOCKED_DEPLOYMENT_CONFLICT';
    }
    return 'BLOCKED_DEPLOYMENT_CONFLICT';
}

function s8_decorate_rebuild_result(array $row): array {
    $section = (string)($row['sectionAction'] ?? $row['status'] ?? '');
    $scorm = (string)($row['scormAction'] ?? '');
    $unitstatus = (string)($row['unitResultStatus'] ?? s7_unit_result_status($row));
    $classification = 'UNCHANGED';
    $action = 'SKIP_UNCHANGED';
    $display = 'Skipped';
    if ($unitstatus === 'FAILED') {
        $classification = 'BLOCKED_DEPLOYMENT_CONFLICT';
        $action = 'FAILED';
        $display = 'Failed';
    } else if (in_array($unitstatus, ['BLOCKED', 'CONFLICT'], true)) {
        $sectionfirst = in_array($section, [
            'UNIT_STAGE_MOVE_REQUIRED',
            'UNIT_SECTION_DUPLICATE',
            'SECTION_MAPPING_CONFLICT',
            'PERMISSION_DENIED',
        ], true);
        $classification = s8_blocked_rebuild_classification($sectionfirst ? $section : ($scorm ?: $section));
        $action = 'BLOCK';
        $display = 'Blocked';
    } else if ($scorm === 'SUPERSEDE_SCORM') {
        $classification = 'REBUILD_WITH_SUPERSESSION';
        $action = 'REBUILD_WITH_SUPERSESSION';
        $display = 'Preserve History';
    } else if (in_array($scorm, ['CREATE_SCORM', 'UPDATE_SCORM'], true)) {
        $classification = 'SAFE_REBUILD';
        $action = 'REBUILD_IN_PLACE';
        $display = 'Rebuild';
    } else if ($scorm === 'UNCHANGED') {
        $classification = 'UNCHANGED';
        $action = 'SKIP_UNCHANGED';
        $display = 'Skipped';
    } else if ($scorm === 'SCORM_DIFF_REQUIRES_PACKAGE') {
        $classification = 'BLOCKED_DEPLOYMENT_CONFLICT';
        $action = 'BLOCK';
        $display = 'Blocked';
    }
    $additional = [];
    if (!empty($row['manualContentPresent'])) {
        $additional[] = 'MANUAL_CONTENT_PRESENT';
    }
    if (!empty($row['legacyUnitCoursePresent'])) {
        $additional[] = 'LEGACY_UNIT_COURSE_PRESENT';
    }
    return array_merge($row, [
        's8RebuildMode' => true,
        's8VisibleOperationName' => 'Rebuild Selected FLW Scope',
        's8RebuildClassification' => $classification,
        's8PlannedAction' => $action,
        's8DisplayAction' => $display,
        's8AdditionalStatuses' => $additional,
        's8LearnerHistoryPresent' => !empty($row['learnerHistoryPresent']),
        's8ManualContentPresent' => !empty($row['manualContentPresent']),
        's8LegacyUnitCoursePresent' => !empty($row['legacyUnitCoursePresent']),
        's8CourseIdStable' => !empty($row['courseId']) && !in_array($row['courseAction'] ?? '', ['CREATE_STAGE_COURSE', 'COURSE_CREATE_FAILED'], true),
        's8SectionIdStable' => !empty($row['sectionId']) && !in_array($section, ['CREATE_SECTION', 'SECTION_CREATE_FAILED'], true),
    ]);
}

function s7_decorate_unit_result(array $row, array $item, string $importmode = 'overwrite'): array {
    $target = s3_target_metadata($item);
    $export = (isset($item['export']) && is_array($item['export'])) ? $item['export'] : [];
    $section = (string)($row['sectionAction'] ?? $row['status'] ?? '');
    $scorm = (string)($row['scormAction'] ?? '');
    $manualpreserved = !in_array($section, [
        'COURSE_NOT_RESOLVED',
        'UNIT_SECTION_DUPLICATE',
        'UNIT_SECTION_TARGET_MISSING',
        'UNIT_STAGE_MOVE_REQUIRED',
        'SECTION_MAPPING_CONFLICT',
        'PERMISSION_DENIED',
        'SECTION_CREATE_FAILED',
        'SECTION_UPDATE_FAILED',
    ], true);
    $attemptspreserved = in_array($scorm, ['UNCHANGED', 'UPDATE_SCORM', 'SUPERSEDE_SCORM'], true) ||
        ($scorm === 'CREATE_SCORM' && empty($row['tracking']));
    $decorated = array_merge($row, [
        'unitResultStatus' => s7_unit_result_status($row),
        'source' => $item['unitPath'] ?? $item['root'] ?? '',
        'worldCode' => $target['worldCode'] ?? $row['worldCode'] ?? '',
        'deploymentStageCode' => $target['deploymentStageCode'] ?? $row['deploymentStageCode'] ?? '',
        'unitSequence' => $target['unitSequence'] ?? $row['unitSequence'] ?? null,
        'courseAction' => $row['courseAction'] ?? '',
        'manualContentPreserved' => $manualpreserved,
        'attemptsPreserved' => $attemptspreserved,
        'packageSha256' => $export['packageSha256'] ?? $item['packageSha256'] ?? '',
        'packageContentSha256' => $export['packageContentSha256'] ?? $item['packageContentSha256'] ?? '',
    ]);
    return s8_is_rebuild_mode($importmode) ? s8_decorate_rebuild_result($decorated) : $decorated;
}

function s7_batch_summary_counts(array $unitresults): array {
    $counts = [];
    foreach ($unitresults as $row) {
        $status = $row['unitResultStatus'] ?? s7_unit_result_status($row);
        $counts[$status] = ($counts[$status] ?? 0) + 1;
    }
    return [
        'unitResultStatusCounts' => $counts,
        'unitsCreated' => $counts['CREATED'] ?? 0,
        'unitsUpdated' => $counts['UPDATED'] ?? 0,
        'unitsSuperseded' => $counts['SUPERSEDED'] ?? 0,
        'unitsUnchanged' => $counts['UNCHANGED'] ?? 0,
        'unitsPending' => $counts['PENDING'] ?? 0,
        'unitsBlocked' => $counts['BLOCKED'] ?? 0,
        'unitsConflict' => $counts['CONFLICT'] ?? 0,
        'unitsFailed' => $counts['FAILED'] ?? 0,
        'manualContentPreserved' => count(array_filter($unitresults, fn($row) => !empty($row['manualContentPreserved']))),
        'attemptsPreserved' => count(array_filter($unitresults, fn($row) => !empty($row['attemptsPreserved']))),
        'scormDiffRequiresPackage' => count(array_filter($unitresults, fn($row) => ($row['scormAction'] ?? '') === 'SCORM_DIFF_REQUIRES_PACKAGE')),
    ];
}

function s8_rebuild_summary_counts(array $unitresults): array {
    $rows = array_values(array_filter($unitresults, fn($row) => !empty($row['s8RebuildMode'])));
    if (!$rows) {
        return [];
    }
    $classcounts = [];
    $actioncounts = [];
    foreach ($rows as $row) {
        $class = $row['s8RebuildClassification'] ?? 'UNKNOWN';
        $action = $row['s8PlannedAction'] ?? 'UNKNOWN';
        $classcounts[$class] = ($classcounts[$class] ?? 0) + 1;
        $actioncounts[$action] = ($actioncounts[$action] ?? 0) + 1;
    }
    return [
        's8Rebuild' => [
            'visibleOperationName' => 'Rebuild Selected FLW Scope',
            'legacyInternalMode' => 'clear_add',
            'safeScopedReplacementForClearAndAdd' => true,
            'selectedUnits' => count($rows),
            'classificationCounts' => $classcounts,
            'actionCounts' => $actioncounts,
            'unitsUnchanged' => $actioncounts['SKIP_UNCHANGED'] ?? 0,
            'unitsRebuiltInPlace' => $actioncounts['REBUILD_IN_PLACE'] ?? 0,
            'unitsRebuiltWithSupersession' => $actioncounts['REBUILD_WITH_SUPERSESSION'] ?? 0,
            'unitsBlocked' => $actioncounts['BLOCK'] ?? 0,
            'unitsFailed' => $actioncounts['FAILED'] ?? 0,
            'historicalScormsPreserved' => count(array_filter($rows, fn($row) => ($row['scormAction'] ?? '') === 'SUPERSEDE_SCORM')),
            'manualObjectsPreserved' => array_sum(array_map(fn($row) => (int)($row['manualContent']['count'] ?? 0), $rows)),
            'legacyCoursesDetected' => array_sum(array_map(fn($row) => (int)($row['legacyUnitCourseCount'] ?? 0), $rows)),
            'learnerHistoryUnitsPreserved' => count(array_filter($rows, fn($row) => !empty($row['learnerHistoryPresent']) && !empty($row['attemptsPreserved']))),
        ],
    ];
}

function flw_import_mode_policy_text(bool $single_direct_import, string $importmode, bool $dryrun): string {
    if (s8_is_rebuild_mode($importmode)) {
        return 'S8 Rebuild Selected FLW Scope is the safe scoped replacement for the legacy destructive clear/add operation: resolve selected World+Stage Courses and Unit Sections, preserve Stage Courses/Unit Sections/manual content, rebuild no-history current SCORMs in place, and supersede history-bearing current SCORMs without deleting learner attempts, grades, completion, or legacy Unit Courses.';
    }
    if ($single_direct_import) {
        if ($importmode === 'add_new') {
            return 'Add New Unit deploys this FLW Unit only when its UnitID is not already present in the canonical Stage Course. If it exists, the importer reports UNIT_ALREADY_EXISTS and tells the user to use Copy Unit first.';
        }
        return 'Overwrite synchronizes this FLW Unit with its canonical Moodle Stage Course, Unit Section, and current Unit SCORM without clearing the Stage Course or deleting neighboring Units.';
    }
    if ($importmode === 'add_new') {
        return 'S7 Batch Add New Unit uses S6 semantics: create only when the canonical UnitID is not already deployed; otherwise report UNIT_ALREADY_EXISTS and continue other independent Units.';
    }
    return 'S7 Batch Overwrite synchronizes canonical Unit deployments by Stage Course group. It never clears Stage Courses or deletes neighboring Units.';
}

function s6_unit_already_exists_for_add_new(array $unitrow): bool {
    $status = (string)($unitrow['status'] ?? '');
    if (in_array($status, ['REUSE_SECTION', 'UPDATE_SECTION', 'REORDER_SECTION'], true)) {
        return true;
    }
    return !empty($unitrow['sectionId']) && $status !== 'CREATE_SECTION';
}

function s6_add_new_unit_already_exists_result(array $item, array $stage_resolution, array $unitrow): array {
    $target = s3_target_metadata($item);
    $unitid = s3_clean_key($target['unitId'] ?? $unitrow['unitId'] ?? '');
    $stagecourse = '';
    $course = $stage_resolution['course'] ?? null;
    if (is_array($course)) {
        $stagecourse = $course['courseFullname'] ?? $course['courseShortname'] ?? $course['courseIdnumber'] ?? '';
    }
    if ($stagecourse === '') {
        $stagecourse = s3_clean_key($target['courseExternalKey'] ?? $unitrow['courseExternalKey'] ?? '');
    }
    $message = ($unitid ?: 'This FLW Unit') . ' is already deployed in ' . ($stagecourse ?: 'the canonical Moodle Stage Course') . '. To create another Unit, use Copy Unit in the Smart Course Editor first, then import the copied Unit.';
    return array_merge($unitrow, [
        'status' => 'UNIT_ALREADY_EXISTS',
        'sectionAction' => 'UNIT_ALREADY_EXISTS',
        'scormAction' => 'UNIT_ALREADY_EXISTS',
        'scormStatus' => 'UNIT_ALREADY_EXISTS',
        'message' => $message,
        'addNewAdvice' => 'Use Copy Unit in the Smart Course Editor first, then import the copied Unit.',
        'scormActivitiesImported' => 0,
    ]);
}

function s6_single_import_request_contract(array $manifest, string $importmode): ?array {
    $items = $manifest['items'] ?? [];
    if (!s6_is_single_direct_import($manifest, $items)) {
        return null;
    }
    $item = $items[0];
    $target = s3_target_metadata($item);
    $export = (isset($item['export']) && is_array($item['export'])) ? $item['export'] : [];
    return [
        'mode' => $importmode,
        'worldCode' => $target['worldCode'] ?? $item['worldCode'] ?? '',
        'deploymentStageCode' => $target['deploymentStageCode'] ?? $item['deploymentStageCode'] ?? '',
        'unitId' => $target['unitId'] ?? $item['unitId'] ?? '',
        'courseExternalKey' => $target['courseExternalKey'] ?? $item['courseExternalKey'] ?? '',
        'unitExternalKey' => $target['unitExternalKey'] ?? $item['unitExternalKey'] ?? '',
        'scormActivityExternalKey' => $target['scormActivityExternalKey'] ?? $item['scormActivityExternalKey'] ?? '',
        'packagePath' => $export['zipPath'] ?? $item['packagePath'] ?? '',
        'packageSha256' => $export['packageSha256'] ?? $item['packageSha256'] ?? '',
        'packageContentSha256' => $export['packageContentSha256'] ?? $item['packageContentSha256'] ?? '',
    ];
}

function s6_public_status(array $summary, array $unitresults): string {
    $statuses = [];
    foreach ($unitresults as $row) {
        $statuses[] = $row['status'] ?? '';
        $statuses[] = $row['scormAction'] ?? '';
    }
    if (($summary['failed'] ?? 0) > 0) {
        if (array_intersect($statuses, ['UNIT_ALREADY_EXISTS', 'UNIT_SECTION_DUPLICATE', 'SCORM_DUPLICATE', 'COURSE_IDNUMBER_CONFLICT', 'SECTION_MAPPING_CONFLICT'])) {
            return 'CONFLICT';
        }
        if (array_intersect($statuses, ['STAGE_UNRESOLVED', 'STAGE_CONFLICT', 'UNIT_STAGE_MOVE_REQUIRED', 'SECTION_NOT_RESOLVED', 'PERMISSION_DENIED', 'CATEGORY_MISSING', 'PREVIEW_STALE'])) {
            return 'BLOCKED';
        }
        return 'FAILED';
    }
    if (count($unitresults) > 0 && count(array_filter($unitresults, fn($row) => ($row['scormAction'] ?? '') === 'UNCHANGED')) === count($unitresults)) {
        return 'UNCHANGED';
    }
    if (($summary['scormDiffRequiresPackage'] ?? 0) > 0) {
        return 'SUCCESS_WITH_WARNINGS';
    }
    if (($summary['legacyUnitCoursesFound'] ?? 0) > 0) {
        return 'SUCCESS_WITH_WARNINGS';
    }
    return 'SUCCESS';
}

function s6_preview_state_payload(array $manifest, array $results, array $unitresults, string $importmode): array {
    $items = $manifest['items'] ?? [];
    $itempayload = [];
    foreach ($items as $item) {
        $target = s3_target_metadata($item);
        $export = (isset($item['export']) && is_array($item['export'])) ? $item['export'] : [];
        $itempayload[] = [
            'worldCode' => $target['worldCode'] ?? $item['worldCode'] ?? '',
            'deploymentStageCode' => $target['deploymentStageCode'] ?? $item['deploymentStageCode'] ?? '',
            'unitId' => $target['unitId'] ?? $item['unitId'] ?? '',
            'courseExternalKey' => $target['courseExternalKey'] ?? $item['courseExternalKey'] ?? '',
            'unitExternalKey' => $target['unitExternalKey'] ?? $item['unitExternalKey'] ?? '',
            'scormActivityExternalKey' => $target['scormActivityExternalKey'] ?? $item['scormActivityExternalKey'] ?? '',
            'packageContentSha256' => $export['packageContentSha256'] ?? $item['packageContentSha256'] ?? '',
        ];
    }
    $resultpayload = array_map(fn($row) => [
        'courseAction' => $row['courseAction'] ?? $row['status'] ?? '',
        'courseExternalKey' => $row['courseExternalKey'] ?? '',
        'courseId' => $row['courseId'] ?? null,
        'legacyUnitCoursesFound' => count(array_filter($row['potentialConflicts'] ?? [], fn($conflict) => ($conflict['status'] ?? '') === 'LEGACY_UNIT_COURSE_FOUND')),
    ], $results);
    $unitpayload = array_map(fn($row) => [
        'unitId' => $row['unitId'] ?? '',
        'sectionAction' => $row['sectionAction'] ?? $row['status'] ?? '',
        'sectionId' => $row['sectionId'] ?? null,
        'sectionNumber' => $row['sectionNumber'] ?? null,
        'scormAction' => $row['scormAction'] ?? '',
        'currentCmid' => $row['currentCmid'] ?? null,
        'historyRisk' => $row['historyRisk'] ?? '',
        'learnerHistoryPresent' => !empty($row['learnerHistoryPresent']),
        'manualContentPresent' => !empty($row['manualContentPresent']),
        'legacyUnitCoursePresent' => !empty($row['legacyUnitCoursePresent']),
        's8RebuildClassification' => $row['s8RebuildClassification'] ?? '',
        's8PlannedAction' => $row['s8PlannedAction'] ?? '',
    ], $unitresults);
    return [
        'importMode' => $importmode,
        'items' => $itempayload,
        'stageCourses' => $resultpayload,
        'unitResults' => $unitpayload,
    ];
}

function s6_preview_state_hash(array $manifest, array $results, array $unitresults, string $importmode): string {
    return hash('sha256', json_encode(s6_preview_state_payload($manifest, $results, $unitresults, $importmode), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
}

function s6_single_import_summary(array $manifest, array $results, array $unitresults, array $summary, string $importmode, bool $dryrun): ?array {
    $items = $manifest['items'] ?? [];
    if (!s6_is_single_direct_import($manifest, $items)) {
        return null;
    }
    $item = $items[0];
    $target = s3_target_metadata($item);
    $course = $results[0] ?? [];
    $unit = $unitresults[0] ?? [];
    $legacycount = (int)($summary['legacyUnitCoursesFound'] ?? 0);
    return [
        'dryRun' => $dryrun,
        'mode' => $importmode,
        'publicStatus' => s6_public_status($summary, $unitresults),
        'flwUnit' => [
            'worldCode' => $target['worldCode'] ?? $unit['worldCode'] ?? '',
            'worldTitle' => $target['worldTitle'] ?? '',
            'sourceStage' => $target['sourceStage'] ?? '',
            'deploymentStageCode' => $target['deploymentStageCode'] ?? $unit['deploymentStageCode'] ?? '',
            'unitId' => $target['unitId'] ?? $unit['unitId'] ?? '',
            'unitTitle' => $target['unitTitle'] ?? $unit['unitTitle'] ?? '',
        ],
        'moodleDestination' => [
            'stageCourseName' => $course['courseFullname'] ?? '',
            'stageCourseKey' => $course['courseExternalKey'] ?? $unit['courseExternalKey'] ?? '',
            'stageCourseUrl' => $course['courseUrl'] ?? '',
            'unitSectionName' => $unit['expectedSectionName'] ?? $unit['sectionName'] ?? '',
            'unitSectionNumber' => $unit['sectionNumber'] ?? $unit['expectedSectionNumber'] ?? null,
            'unitSectionUrl' => $unit['sectionUrl'] ?? '',
            'unitScormName' => 'Unit SCORM',
            'unitScormUrl' => $unit['viewUrl'] ?? '',
        ],
        'plannedAction' => [
            'course' => $course['courseAction'] ?? $course['status'] ?? '',
            'section' => $unit['sectionAction'] ?? $unit['status'] ?? '',
            'scorm' => $unit['scormAction'] ?? '',
        ],
        'historySafety' => [
            'learnerAttempts' => !empty($unit['tracking']['attempts']) ? 'attempts detected' : 'no tracked attempts detected',
            'deploymentStrategy' => ($unit['scormAction'] ?? '') === 'SUPERSEDE_SCORM'
                ? 'Supersession'
                : (($unit['scormAction'] ?? '') === 'UPDATE_SCORM' ? 'Safe in-place update' : (($unit['scormAction'] ?? '') === 'UNCHANGED' ? 'No package change' : 'New Unit SCORM')),
            'historyRisk' => $unit['historyRisk'] ?? 'NONE',
        ],
        'manualTeacherContent' => 'preserved',
        'legacyWarning' => $legacycount > 0 ? 'LEGACY_UNIT_COURSE_FOUND: legacy Unit Course detected and left untouched.' : '',
        'message' => $unit['message'] ?? $course['message'] ?? '',
    ];
}

// Legacy pre-S3 pilot path: Unit -> Moodle Course.
// Normal production imports use import_by_language(), resolve_stage_course_group(),
// resolve_unit_section(), and deploy_unit_scorm_activity() instead. Keep this
// block only for historical CLI compatibility; do not route Program-1 imports here.
function language_course_definition(array $item): array {
    $code = strtolower((string)($item['code'] ?? ''));
    $unit = item_unit_number($item);
    $padded = sprintf('%03d', $unit);
    $unitgroup = unit_search_terms($unit);
    $catalog = [
        '01-adventure' => [
            'language' => 'Adventure English',
            'category' => 12,
            'categories' => [12],
            'fullnamePattern' => 'Adventure English World V2 Unit %s',
            'shortnamePattern' => 'AEW2 U%s',
            'matchLanguageTerms' => ['adventure english world v2', 'adventure english world', 'aew2'],
            'fixedUnit001CourseId' => 101,
        ],
        '02-real' => [
            'language' => 'Real English',
            'category' => 13,
            'categories' => [13],
            'fullnamePattern' => 'Real English World V2 Unit %s',
            'shortnamePattern' => 'REW2 U%s',
            'matchLanguageTerms' => ['real english world v2', 'real english world', 'rew2', 'rew'],
            'fixedUnit001CourseId' => 114,
        ],
        '03-russian' => [
            'language' => 'Russian',
            'category' => 25,
            'categories' => [25],
            'fullnamePattern' => 'Russian World V2 Unit %s',
            'shortnamePattern' => 'RUW2 U%s',
            'matchLanguageTerms' => ['russian world v2', 'russian world', 'ruw2'],
            'fixedUnit001CourseId' => 116,
        ],
        '04-chinese' => [
            'language' => 'Chinese',
            'category' => 95,
            'categories' => [95],
            'fullnamePattern' => 'Chinese World V2 Unit %s',
            'shortnamePattern' => 'CHW2 U%s',
            'matchLanguageTerms' => ['chinese world v2', 'chinese world', 'chw2'],
            'fixedUnit001CourseId' => 118,
        ],
        '05-german' => [
            'language' => 'German',
            'category' => 48,
            'categories' => [48],
            'fullnamePattern' => 'German World V2 Unit %s',
            'shortnamePattern' => 'GEW2 U%s',
            'matchLanguageTerms' => ['german world v2', 'german world', 'gew2'],
            'fixedUnit001CourseId' => 120,
        ],
        '06-japanese' => [
            'language' => 'Japanese',
            'category' => 60,
            'categories' => [60],
            'fullnamePattern' => 'Japanese World V2 Unit %s',
            'shortnamePattern' => 'JPW2 U%s',
            'matchLanguageTerms' => ['japanese world v2', 'japanese world', 'jpw2'],
            'fixedUnit001CourseId' => 122,
        ],
        '07-spanish' => [
            'language' => 'Spanish',
            'category' => 72,
            'categories' => [72],
            'fullnamePattern' => 'Spanish World Unit %s',
            'shortnamePattern' => 'SW_U%s',
            'matchLanguageTerms' => ['spanish world', 'sw_u', 'spanish'],
        ],
        '08-french' => [
            'language' => 'French',
            'category' => 84,
            'categories' => [84],
            'fullnamePattern' => 'French World Unit %s',
            'shortnamePattern' => 'FW_U%s',
            'matchLanguageTerms' => ['french world', 'fw_u', 'french'],
            'fixedUnit001CourseId' => 176,
        ],
    ];

    if (isset($catalog[$code])) {
        $base = $catalog[$code];
        $definition = $base + [
            'code' => $code,
            'unit' => $unit,
            'unitPadded' => $padded,
        ];
        $definition['fullname'] = sprintf($base['fullnamePattern'], $padded);
        $definition['shortname'] = sprintf($base['shortnamePattern'], $padded);
        $definition['matchGroups'] = [$base['matchLanguageTerms'], $unitgroup];
        if ($unit === 1 && !empty($base['fixedUnit001CourseId'])) {
            $definition['fixedCourseId'] = (int)$base['fixedUnit001CourseId'];
        }
        return $definition;
    }

    $label = clean_short_text($item['label'] ?? 'Unknown Language', 80) ?: 'Unknown Language';
    $shortlabel = strtoupper(preg_replace('/[^A-Za-z0-9]+/', '', $label)) ?: 'FLW';
    return [
        'code' => $code,
        'language' => $label,
        'unit' => $unit,
        'unitPadded' => $padded,
        'category' => 1,
        'categories' => [],
        'fullname' => $label . ' Unit ' . $padded,
        'shortname' => clean_short_text($shortlabel . ' U' . $padded, 100),
        'matchGroups' => [[$label], $unitgroup],
    ];
}

function lower_match_text(string $text): string {
    return function_exists('mb_strtolower') ? mb_strtolower($text, 'UTF-8') : strtolower($text);
}

function haystack_has_term(string $haystack, string $term): bool {
    $needle = lower_match_text($term);
    if (preg_match('/^unit\s*0*(\d+)$/', $needle, $matches)) {
        return preg_match('/\bunit\s*0*' . preg_quote($matches[1], '/') . '(?!\d)/u', $haystack) === 1;
    }
    if (preg_match('/^u0*(\d+)$/', $needle, $matches)) {
        return preg_match('/\bu0*' . preg_quote($matches[1], '/') . '(?!\d)/u', $haystack) === 1;
    }
    return $needle !== '' && strpos($haystack, $needle) !== false;
}

function find_existing_language_course(array $definition): ?stdClass {
    global $DB;

    $groups = $definition['matchGroups'] ?? [];
    if (!$groups) {
        return null;
    }
    $categories = array_map('intval', $definition['categories'] ?? []);
    $courses = $DB->get_records('course', null, 'id ASC', 'id,shortname,fullname,category');

    foreach ($courses as $course) {
        if ($categories && !in_array((int)$course->category, $categories, true)) {
            continue;
        }
        $haystack = lower_match_text((string)$course->shortname . ' ' . (string)$course->fullname);
        $matches = true;
        foreach ($groups as $group) {
            $groupmatch = false;
            foreach ($group as $term) {
                if (haystack_has_term($haystack, (string)$term)) {
                    $groupmatch = true;
                    break;
                }
            }
            if (!$groupmatch) {
                $matches = false;
                break;
            }
        }
        if ($matches) {
            return $course;
        }
    }
    return null;
}

function find_corresponding_language_course(array $definition): ?stdClass {
    global $DB;

    $matchedcourse = find_existing_language_course($definition);
    if ($matchedcourse) {
        return $matchedcourse;
    }
    if (!empty($definition['fixedCourseId'])) {
        $course = $DB->get_record('course', ['id' => (int)$definition['fixedCourseId']], '*', IGNORE_MISSING);
        if ($course) {
            return $course;
        }
    }
    if (!empty($definition['shortname'])) {
        $course = $DB->get_record('course', ['shortname' => $definition['shortname']], '*', IGNORE_MISSING);
        if ($course) {
            return $course;
        }
    }
    return null;
}

function moodle_course_table_name(): string {
    global $CFG;

    return preg_replace('/[^A-Za-z0-9_]+/', '', (string)$CFG->prefix) . 'course';
}

function pg_identifier_path(string $path): string {
    $parts = array_values(array_filter(explode('.', $path), fn($part) => $part !== ''));
    if (!$parts) {
        return '""';
    }
    return implode('.', array_map(fn($part) => '"' . str_replace('"', '""', $part) . '"', $parts));
}

function current_moodle_course_sequence_next_id(): ?int {
    global $DB;

    $family = method_exists($DB, 'get_dbfamily') ? $DB->get_dbfamily() : '';
    $table = moodle_course_table_name();
    try {
        if ($family === 'mysql') {
            $next = $DB->get_field_sql(
                'SELECT AUTO_INCREMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?',
                [$table]
            );
            return is_numeric($next) ? (int)$next : null;
        }
        if ($family === 'postgres') {
            $sequence = $DB->get_field_sql("SELECT pg_get_serial_sequence('{$table}', 'id')");
            if (!$sequence) {
                return null;
            }
            $record = $DB->get_record_sql('SELECT last_value, is_called FROM ' . pg_identifier_path((string)$sequence));
            if (!$record) {
                return null;
            }
            $iscalled = is_bool($record->is_called)
                ? $record->is_called
                : in_array(strtolower((string)$record->is_called), ['1', 't', 'true', 'y', 'yes'], true);
            return $iscalled ? ((int)$record->last_value + 1) : (int)$record->last_value;
        }
    } catch (Throwable $e) {
        return null;
    }
    return null;
}

function next_course_id(int $minimum = MOODLE_COURSE_ID_FLOOR): int {
    global $DB;

    $maxid = (int)$DB->get_field_sql('SELECT MAX(id) FROM {course}');
    $sequencenext = current_moodle_course_sequence_next_id();
    return max(1, $minimum, $maxid + 1, (int)($sequencenext ?? 0));
}

function ensure_moodle_course_id_floor(int $minimum = MOODLE_COURSE_ID_FLOOR): array {
    global $DB;

    $minimum = max(1, (int)$minimum);
    $maxid = (int)$DB->get_field_sql('SELECT MAX(id) FROM {course}');
    $sequencenext = current_moodle_course_sequence_next_id();
    $currentnextid = max($maxid + 1, (int)($sequencenext ?? 0));
    $targetnextid = max($minimum, $maxid + 1, $currentnextid);
    $family = method_exists($DB, 'get_dbfamily') ? $DB->get_dbfamily() : '';
    $result = [
        'status' => 'already_at_or_above_floor',
        'dbFamily' => $family,
        'minimumCourseId' => $minimum,
        'maxCourseId' => $maxid,
        'sequenceNextCourseId' => $sequencenext,
        'nextCourseId' => $targetnextid,
    ];

    if ($currentnextid >= $minimum) {
        return $result;
    }

    try {
        if ($family === 'mysql') {
            $DB->execute('ALTER TABLE {course} AUTO_INCREMENT = ' . $targetnextid);
            $result['status'] = 'raised';
            return $result;
        }
        if ($family === 'postgres') {
            $table = moodle_course_table_name();
            $DB->execute("SELECT setval(pg_get_serial_sequence('{$table}', 'id'), " . ($targetnextid - 1) . ', true)');
            $result['status'] = 'raised';
            return $result;
        }
    } catch (Throwable $e) {
        $result['status'] = 'failed';
        $result['error'] = $e->getMessage();
        throw new RuntimeException(
            'Could not raise Moodle course ID sequence to the required floor ' . $minimum . ': ' . $e->getMessage(),
            0,
            $e
        );
    }

    if ($maxid + 1 < $minimum) {
        $result['status'] = 'not_supported';
        throw new RuntimeException(
            'Could not verify Moodle course ID floor ' . $minimum . ' for database family "' . $family . '".'
        );
    }

    return $result;
}

function course_category_for_definition(array $definition): int {
    global $DB;

    $category = (int)($definition['category'] ?? 1);
    if ($category > 0 && $DB->record_exists('course_categories', ['id' => $category])) {
        return $category;
    }
    return 1;
}

function unique_course_shortname(string $base, ?int $plannedid = null, bool $forcecopy = false): string {
    global $DB;

    $base = clean_short_text(preg_replace('/\s+/u', ' ', trim($base)), 90);
    if ($base === '') {
        $base = 'FLW Unit';
    }
    if (!$forcecopy && !$DB->record_exists('course', ['shortname' => $base])) {
        return $base;
    }
    $suffixes = [];
    if ($plannedid) {
        $suffixes[] = ' CID' . (int)$plannedid;
    }
    $suffixes[] = ' ' . date('YmdHis');
    for ($index = 2; $index < 1000; $index++) {
        foreach ($suffixes as $suffix) {
            $candidate = clean_short_text($base . $suffix . ($index === 2 ? '' : '-' . $index), 100);
            if (!$DB->record_exists('course', ['shortname' => $candidate])) {
                return $candidate;
            }
        }
    }
    throw new moodle_exception('duplicateshortname', 'error', '', $base);
}

function create_language_course(array $definition, string $importmode): stdClass {
    ensure_moodle_course_id_floor();
    $plannedid = next_course_id();
    $newcourse = new stdClass();
    $fullname = clean_short_text($definition['fullname'] ?? (($definition['language'] ?? 'FLW') . ' Unit ' . ($definition['unitPadded'] ?? '001')), 254);
    if ($importmode === 'add_new') {
        $fullname = clean_short_text($fullname . ' (Course ' . $plannedid . ')', 254);
    }
    $newcourse->fullname = $fullname;
    $newcourse->shortname = unique_course_shortname((string)($definition['shortname'] ?? $fullname), $plannedid, $importmode === 'add_new');
    $newcourse->category = course_category_for_definition($definition);
    $newcourse->summary = '<p>Language course created by Smart Course editor FLW import.</p>';
    $newcourse->summaryformat = FORMAT_HTML;
    $newcourse->format = 'topics';
    $newcourse->numsections = 10;
    $newcourse->visible = 1;
    $newcourse->newsitems = 0;
    $newcourse->startdate = time();
    return create_course($newcourse);
}

// Legacy destructive Unit-course helper. Normal production imports must not call
// this function; S8/S9 smoke tests assert it is absent from import_by_language().
function clear_course_for_overwrite(stdClass $course, bool $dryrun): array {
    global $DB;

    $modules = $DB->count_records('course_modules', ['course' => $course->id]);
    $sections = $DB->count_records_select('course_sections', 'course = :course AND section > 0', ['course' => $course->id]);
    $report = [
        'courseId' => (int)$course->id,
        'courseFullname' => $course->fullname,
        'courseShortname' => $course->shortname,
        'modulesBefore' => $modules,
        'sectionsBefore' => $sections,
        'dryRun' => $dryrun,
        'cleared' => false,
    ];
    if ($dryrun) {
        return $report;
    }
    if (function_exists('remove_course_contents')) {
        remove_course_contents($course->id, false);
    } else {
        $cms = $DB->get_records('course_modules', ['course' => $course->id], 'id ASC', 'id');
        foreach ($cms as $cm) {
            course_delete_module((int)$cm->id);
        }
    }
    rebuild_course_cache($course->id, true);
    $report['cleared'] = true;
    $report['modulesAfter'] = $DB->count_records('course_modules', ['course' => $course->id]);
    return $report;
}

function course_summary_row(stdClass $course): array {
    return [
        'courseId' => (int)$course->id,
        'fullname' => $course->fullname,
        'shortname' => $course->shortname,
        'category' => (int)$course->category,
    ];
}

// Legacy destructive Unit-course helper. Normal production imports must not call
// this function; S8/S9 smoke tests assert it is absent from import_by_language().
function reset_course_id_sequence(int $nextid): array {
    global $DB, $CFG;

    $family = method_exists($DB, 'get_dbfamily') ? $DB->get_dbfamily() : '';
    try {
        if ($family === 'mysql') {
            $DB->execute('ALTER TABLE {course} AUTO_INCREMENT = ' . (int)$nextid);
            return ['status' => 'reset', 'dbFamily' => $family, 'nextCourseId' => $nextid];
        }
        if ($family === 'postgres') {
            $table = preg_replace('/[^A-Za-z0-9_]+/', '', (string)$CFG->prefix) . 'course';
            $DB->execute("SELECT setval(pg_get_serial_sequence('{$table}', 'id'), " . ((int)$nextid - 1) . ', true)');
            return ['status' => 'reset', 'dbFamily' => $family, 'nextCourseId' => $nextid];
        }
    } catch (Throwable $e) {
        return ['status' => 'failed', 'dbFamily' => $family, 'nextCourseId' => $nextid, 'error' => $e->getMessage()];
    }
    return ['status' => 'not_supported', 'dbFamily' => $family, 'nextCourseId' => $nextid];
}

// Legacy destructive Unit-course helper. Normal production imports must not call
// this function; S8/S9 smoke tests assert it is absent from import_by_language().
function clear_courses_above_id(int $threshold, bool $dryrun, int $resetstart = MOODLE_COURSE_ID_FLOOR): array {
    global $DB;

    $courses = $DB->get_records_select('course', 'id > :threshold', ['threshold' => $threshold], 'id ASC');
    $report = [
        'threshold' => $threshold,
        'resetStart' => $resetstart,
        'dryRun' => $dryrun,
        'count' => count($courses),
        'deleted' => 0,
        'courses' => array_map(fn($course) => course_summary_row($course), array_values($courses)),
        'sequence' => null,
    ];
    if ($dryrun) {
        return $report;
    }
    foreach ($courses as $course) {
        if ((int)$course->id <= 1) {
            continue;
        }
        if (!delete_course($course, false)) {
            throw new moodle_exception('coursedeletionfailed', 'error', '', $course->id);
        }
        $report['deleted']++;
    }
    $report['sequence'] = reset_course_id_sequence($resetstart);
    purge_all_caches();
    return $report;
}

function resolve_language_course(array $item, bool $dryrun, string $importmode = 'overwrite', ?int $plannedcourseid = null): array {
    $definition = language_course_definition($item);
    $plannedcourseid = $plannedcourseid ?: next_course_id();

    if ($importmode === 'add_new' || $importmode === 'clear_add') {
        if ($dryrun) {
            return ['course' => null, 'created' => false, 'wouldCreate' => true, 'overwrite' => false, 'plannedCourseId' => $plannedcourseid, 'definition' => $definition];
        }
        $course = create_language_course($definition, $importmode);
        return ['course' => $course, 'created' => true, 'wouldCreate' => false, 'overwrite' => false, 'plannedCourseId' => (int)$course->id, 'definition' => $definition];
    }

    $matchedcourse = find_corresponding_language_course($definition);
    if ($matchedcourse) {
        return ['course' => $matchedcourse, 'created' => false, 'wouldCreate' => false, 'overwrite' => true, 'plannedCourseId' => null, 'definition' => $definition];
    }
    if ($dryrun) {
        return ['course' => null, 'created' => false, 'wouldCreate' => true, 'overwrite' => false, 'plannedCourseId' => $plannedcourseid, 'definition' => $definition];
    }
    $course = create_language_course($definition, $importmode);
    return ['course' => $course, 'created' => true, 'wouldCreate' => false, 'overwrite' => false, 'plannedCourseId' => (int)$course->id, 'definition' => $definition];
}

function import_by_language(array $manifest, string $manifestpath, string $stamp, string $sectionname, bool $dryrun, string $nameprefix = 'SCORM Pilot', string $importmode = 'overwrite', ?string $stage_map_path = null, ?string $unit_section_map_path = null, ?string $unit_scorm_map_path = null, bool $force_supersede = false): array {
    global $CFG, $DB;

    $importmode = normalize_import_mode($importmode);
    $items = $manifest['items'] ?? [];
    $map_path = stage_course_map_path($stage_map_path);
    $section_map_path = unit_section_map_path($unit_section_map_path);
    $scorm_map_path = unit_scorm_map_path($unit_scorm_map_path);
    $groups = stage_course_groups($items, ['exported']);
    $single_direct_import = s6_is_single_direct_import($manifest, $items);
    $results = [];
    $unitresults = [];
    $order_moves = [];
    $createdcourses = [];
    $failures = 0;

    $clearoperation = null;
    if ($importmode === 'clear_add') {
        $clearoperation = [
            'status' => 'SAFE_SCOPED_REBUILD',
            'visibleOperationName' => 'Rebuild Selected FLW Scope',
            'message' => 'Internal clear_add compatibility mode is S8 safe scoped rebuild. It does not delete numeric Moodle course ranges, reset IDs, clear Stage Courses, or modify legacy Unit Courses.',
            'deleted' => 0,
            'scopeModel' => 'WorldCode + DeploymentStageCode + UnitID + UnitSCORMActivityID',
        ];
    }

    foreach ($groups as $group) {
        $resolution = resolve_stage_course_group($group, $dryrun, $map_path, true);
        $resolution['courseImage'] = sync_stage_course_image($group, $resolution, $dryrun);
        $row = stage_result_public_row($resolution);
        $row['importMode'] = $importmode;
        $row['dryRun'] = $dryrun;
        $row['futureUnitAction'] = 'UNIT_SECTION_RESOLVED_S4';
        $row['futureScormAction'] = 'UNIT_SCORM_UPSERT_S5';
        $results[] = $row;

        if (!empty($resolution['created']) && !empty($row['courseId'])) {
            $createdcourses[] = [
                'courseId' => $row['courseId'],
                'fullname' => $row['courseFullname'],
                'shortname' => $row['courseShortname'],
                'idnumber' => $row['courseIdnumber'],
            ];
        }
        if (in_array($row['status'], ['COURSE_IDNUMBER_CONFLICT', 'CATEGORY_MISSING', 'STAGE_UNRESOLVED', 'STAGE_CONFLICT', 'PERMISSION_DENIED', 'COURSE_CREATE_FAILED'], true)) {
            $failures++;
        }
        if (course_image_failure_status((string)($row['courseImage']['status'] ?? ''))) {
            $failures++;
        }
        $groupunitresults = [];
        foreach ($group['items'] as $item) {
            $unitrow = resolve_unit_section($item, $resolution, $dryrun, $section_map_path);
            if (s7_enforces_unique_unit_for_add_new($manifest, $items, $importmode) && s6_unit_already_exists_for_add_new($unitrow)) {
                $unitrow = s6_add_new_unit_already_exists_result($item, $resolution, $unitrow);
            }
            $groupunitresults[] = $unitrow;
            if (in_array(($unitrow['status'] ?? ''), ['COURSE_NOT_RESOLVED', 'UNIT_ALREADY_EXISTS', 'UNIT_SECTION_DUPLICATE', 'UNIT_SECTION_TARGET_MISSING', 'UNIT_STAGE_MOVE_REQUIRED', 'SECTION_MAPPING_CONFLICT', 'PERMISSION_DENIED', 'SECTION_CREATE_FAILED', 'SECTION_UPDATE_FAILED'], true)) {
                $failures++;
            }
        }
        $courseid = (int)($row['courseId'] ?? 0);
        if ($courseid > 0 && !unit_section_rows_have_blockers($groupunitresults)) {
            $course = $DB->get_record('course', ['id' => $courseid], '*', IGNORE_MISSING);
            if ($course) {
                $moves = enforce_unit_section_order($course, $dryrun);
                $order_moves = array_merge($order_moves, $moves);
                $groupunitresults = apply_order_moves_to_unit_results($groupunitresults, $moves);
                if (!$dryrun) {
                    refresh_unit_section_group_mappings($group['items'], $groupunitresults, $course, $section_map_path);
                }
                foreach ($moves as $move) {
                    if (in_array(($move['status'] ?? ''), ['PERMISSION_DENIED', 'SECTION_REORDER_FAILED'], true)) {
                        $failures++;
                    }
                }
            }
        }

        foreach ($groupunitresults as $index => $unitrow) {
            if (($unitrow['status'] ?? '') === 'UNIT_ALREADY_EXISTS') {
                $groupunitresults[$index] = s7_decorate_unit_result($unitrow, $group['items'][$index], $importmode);
                continue;
            }
            $scormrow = deploy_unit_scorm_activity($group['items'][$index], $resolution, $unitrow, $dryrun, $scorm_map_path, $force_supersede, s8_is_rebuild_mode($importmode));
            $filepoolretries = 0;
            while (!$dryrun && $filepoolretries < 4 && scorm_filepool_failure_is_retryable($scormrow)) {
                $filepoolretries++;
                $retryunit = (string)($unitrow['unitId'] ?? $unitrow['UnitID'] ?? ('unit-' . $index));
                mtrace('[S5 FILEPOOL_RETRY] ' . $retryunit . ' attempt ' . $filepoolretries . '/4');
                // Each failed update transaction is rolled back inside
                // deploy_unit_scorm_activity(). Give Windows file scanners time
                // to release the just-extracted payload, then repeat the same
                // identity-preserving Moodle update transaction.
                usleep(1000000 * $filepoolretries);
                $scormrow = deploy_unit_scorm_activity(
                    $group['items'][$index],
                    $resolution,
                    $unitrow,
                    false,
                    $scorm_map_path,
                    $force_supersede,
                    s8_is_rebuild_mode($importmode)
                );
            }
            if ($filepoolretries > 0) {
                $scormrow['filePoolRetryCount'] = $filepoolretries;
                $scormrow['filePoolRetryResult'] = scorm_filepool_failure_is_retryable($scormrow)
                    ? 'EXHAUSTED'
                    : 'RECOVERED';
            }
            $merged = array_merge($unitrow, $scormrow);
            $merged = s7_decorate_unit_result($merged, $group['items'][$index], $importmode);
            $groupunitresults[$index] = $merged;
            $scormsummary = unit_scorm_summary_counts([$merged]);
            $failures += (int)($scormsummary['scormFailures'] ?? 0);
        }

        $unitresults = array_merge($unitresults, $groupunitresults);
        $groupScormCounts = unit_scorm_summary_counts($groupunitresults);
        mtrace('[S5 ' . ($row['status'] ?: 'unknown') . '] ' . ($row['courseExternalKey'] ?: 'unresolved') .
            ' units=' . ($row['unitCount'] ?? 0) .
            ' scorm=create ' . ($groupScormCounts['scormCreated'] ?? 0) .
            ', update ' . ($groupScormCounts['scormUpdated'] ?? 0) .
            ', unchanged ' . ($groupScormCounts['scormUnchanged'] ?? 0) .
            ', supersede ' . ($groupScormCounts['scormSuperseded'] ?? 0) .
            ', failures ' . ($groupScormCounts['scormFailures'] ?? 0));
    }

    $summary = unit_section_summary($results, $unitresults, $order_moves);
    $summary = array_merge($summary, unit_scorm_summary_counts($unitresults));
    $summary = array_merge($summary, s7_batch_summary_counts($unitresults));
    $summary = array_merge($summary, s8_rebuild_summary_counts($unitresults));
    $summary['createdCourses'] = count($createdcourses);
    $summary['deletedCourses'] = 0;
    $summary['overwrittenCourses'] = 0;
    $summary['imported'] = $summary['scormActivitiesImported'] ?? 0;
    $summary['alreadyExists'] = $summary['scormUnchanged'] ?? 0;
    $summary['dryRunReady'] = 0;
    $summary['failed'] = $failures;
    $summary['publicStatus'] = s6_public_status($summary, $unitresults);
    $previewstatehash = s6_preview_state_hash($manifest, $results, $unitresults, $importmode);
    $singleimportsummary = s6_single_import_summary($manifest, $results, $unitresults, $summary, $importmode, $dryrun);

    return [
        'kind' => 'smartcourses_unit_scorm_upsert',
        'mode' => $single_direct_import ? 'single_unit_scorm_upsert' : 'unit_scorm_upsert',
        'architecture' => 'FLW World + Deployment Stage -> Moodle Course; FLW Unit -> Moodle Section; 1 FLW Unit -> 1 SCORM 1.2 activity/package; substantial component -> 1 SCO',
        's5Only' => !$single_direct_import,
        's6SingleImport' => $single_direct_import,
        's7BatchImport' => s7_is_batch_manifest($manifest),
        'batchGroupingMethod' => 'WorldCode + DeploymentStageCode; Stage Course resolver executes once per group before Unit Section and Unit SCORM upsert.',
        'importMode' => $importmode,
        's8RebuildMode' => s8_is_rebuild_mode($importmode),
        'visibleOperationName' => s8_is_rebuild_mode($importmode) ? 'Rebuild Selected FLW Scope' : '',
        'importModePolicy' => flw_import_mode_policy_text($single_direct_import, $importmode, $dryrun),
        'batchStatusContract' => [
            'job' => ['PENDING', 'PREFLIGHT', 'RUNNING', 'CANCELLING', 'CANCELLED', 'SUCCEEDED', 'SUCCEEDED_WITH_WARNINGS', 'PARTIAL', 'FAILED', 'RESUMABLE'],
            'unit' => ['PENDING', 'RUNNING', 'CREATED', 'UPDATED', 'SUPERSEDED', 'UNCHANGED', 'SKIPPED', 'BLOCKED', 'CONFLICT', 'FAILED'],
        ],
        'batchPlanId' => $manifest['batchPlanId'] ?? '',
        'stageGroups' => $manifest['stageGroups'] ?? [],
        'catalogValidation' => $manifest['catalogValidation'] ?? null,
        'dryRun' => $dryrun,
        'requestContract' => s6_single_import_request_contract($manifest, $importmode),
        'previewStateHash' => $previewstatehash,
        'singleImport' => $singleimportsummary,
        'destructivePathGuard' => [
            'singleOverwriteClearsStageCourse' => false,
            'clear_course_for_overwrite_reachable' => false,
            'clear_courses_above_id_reachable' => false,
            'reset_course_id_sequence_reachable' => false,
            'delete_course_reachable' => false,
            'course_delete_module_reachable_for_manual_content' => false,
            'legacyDestructiveHelpers' => 'isolated_legacy_development_only',
        ],
        'manifestPath' => $manifestpath,
        'moodleUrl' => rtrim((string)$CFG->wwwroot, '/'),
        'timestamp' => $stamp,
        'stageCourseMapPath' => $map_path,
        'unitSectionMapPath' => $section_map_path,
        'unitScormMapPath' => $scorm_map_path,
        'markerMethod' => 'COURSE_SECTION_SUMMARY_HTML_COMMENT',
        'scormIdentityMethod' => 'stable cmidnumber + UnitSCORMActivityID + SCORM manifest/SCO identifiers',
        'forceSupersede' => $force_supersede,
        'clearOperation' => $clearoperation,
        'createdCourses' => $createdcourses,
        'results' => $results,
        'unitResults' => $unitresults,
        'orderMoves' => $order_moves,
        'summary' => $summary,
    ];
}

function preview_course_map(array $manifest, string $manifestpath, string $stamp, string $importmode = 'overwrite', ?string $stage_map_path = null, ?string $unit_section_map_path = null, ?string $unit_scorm_map_path = null, bool $force_supersede = false): array {
    global $CFG, $DB;

    $importmode = normalize_import_mode($importmode);
    $items = $manifest['items'] ?? [];
    $map_path = stage_course_map_path($stage_map_path);
    $section_map_path = unit_section_map_path($unit_section_map_path);
    $scorm_map_path = unit_scorm_map_path($unit_scorm_map_path);
    $groups = stage_course_groups($items, ['planned', 'exported']);
    $single_direct_import = s6_is_single_direct_import($manifest, $items);
    $results = [];
    $unitresults = [];
    $order_moves = [];
    if ($importmode === 'clear_add') {
        $clearoperation = [
            'status' => 'SAFE_SCOPED_REBUILD_PREVIEW',
            'visibleOperationName' => 'Rebuild Selected FLW Scope',
            'message' => 'Read-only S8 rebuild preview. It does not hide, delete, create, update, archive, or reset anything.',
            'count' => 0,
            'scopeModel' => 'WorldCode + DeploymentStageCode + UnitID + UnitSCORMActivityID',
        ];
    } else {
        $clearoperation = null;
    }

    foreach ($groups as $group) {
        $resolution = resolve_stage_course_group($group, true, $map_path, false);
        $resolution['courseImage'] = sync_stage_course_image($group, $resolution, true);
        $row = stage_result_public_row($resolution);
        $row['importMode'] = $importmode;
        $row['dryRun'] = true;
        $row['futureUnitAction'] = 'UNIT_SECTION_RESOLVED_S4';
        $row['futureScormAction'] = 'UNIT_SCORM_UPSERT_S5';
        $results[] = $row;
        $groupunitresults = [];
        foreach ($group['items'] as $item) {
            $unitrow = resolve_unit_section($item, $resolution, true, $section_map_path);
            if (s7_enforces_unique_unit_for_add_new($manifest, $items, $importmode) && s6_unit_already_exists_for_add_new($unitrow)) {
                $unitrow = s6_add_new_unit_already_exists_result($item, $resolution, $unitrow);
            }
            $groupunitresults[] = $unitrow;
        }
        $courseid = (int)($row['courseId'] ?? 0);
        if ($courseid > 0 && !unit_section_rows_have_blockers($groupunitresults)) {
            $course = $DB->get_record('course', ['id' => $courseid], '*', IGNORE_MISSING);
            if ($course) {
                $moves = enforce_unit_section_order($course, true);
                $order_moves = array_merge($order_moves, $moves);
                $groupunitresults = apply_order_moves_to_unit_results($groupunitresults, $moves);
            }
        }
        foreach ($groupunitresults as $index => $unitrow) {
            if (($unitrow['status'] ?? '') === 'UNIT_ALREADY_EXISTS') {
                $groupunitresults[$index] = s7_decorate_unit_result($unitrow, $group['items'][$index], $importmode);
                continue;
            }
            if (s7_is_batch_mapping_preview($manifest) && !s7_item_has_package_path($group['items'][$index])) {
                $groupunitresults[$index] = s7_decorate_unit_result(
                    s7_scorm_diff_requires_package_result($group['items'][$index], $unitrow),
                    $group['items'][$index],
                    $importmode
                );
                continue;
            }
            $scormrow = deploy_unit_scorm_activity($group['items'][$index], $resolution, $unitrow, true, $scorm_map_path, $force_supersede, s8_is_rebuild_mode($importmode));
            $groupunitresults[$index] = s7_decorate_unit_result(array_merge($unitrow, $scormrow), $group['items'][$index], $importmode);
        }
        $unitresults = array_merge($unitresults, $groupunitresults);
    }

    $summary = unit_section_summary($results, $unitresults, $order_moves);
    $summary = array_merge($summary, unit_scorm_summary_counts($unitresults));
    $summary = array_merge($summary, s7_batch_summary_counts($unitresults));
    $summary = array_merge($summary, s8_rebuild_summary_counts($unitresults));
    $summary['mapped'] = $summary['reusedStageCourses'];
    $summary['wouldCreateCourse'] = $summary['wouldCreateStageCourses'];
    $summary['wouldOverwriteCourse'] = 0;
    $summary['wouldDeleteCourse'] = 0;
    $summary['missingCourse'] = $summary['conflictCount'];
    $summary['failed'] = ($summary['conflictCount'] ?? 0) + ($summary['unitSectionFailures'] ?? 0) + ($summary['scormFailures'] ?? 0) + ($summary['courseImageFailures'] ?? 0);
    $summary['total'] = count($results);
    $summary['publicStatus'] = s6_public_status($summary, $unitresults);
    $previewstatehash = s6_preview_state_hash($manifest, $results, $unitresults, $importmode);
    $singleimportsummary = s6_single_import_summary($manifest, $results, $unitresults, $summary, $importmode, true);

    return [
        'kind' => 'smartcourses_unit_scorm_preview',
        'mode' => $single_direct_import ? 'single_unit_scorm_preview' : 'unit_scorm_preview',
        'architecture' => 'FLW World + Deployment Stage -> Moodle Course; FLW Unit -> Moodle Section; 1 FLW Unit -> 1 SCORM 1.2 activity/package; substantial component -> 1 SCO',
        's5Only' => !$single_direct_import,
        's6SingleImport' => $single_direct_import,
        's7BatchImport' => s7_is_batch_manifest($manifest),
        'batchGroupingMethod' => 'WorldCode + DeploymentStageCode; preview resolves each Stage Course group once, then Unit Sections.',
        'importMode' => $importmode,
        's8RebuildMode' => s8_is_rebuild_mode($importmode),
        'visibleOperationName' => s8_is_rebuild_mode($importmode) ? 'Rebuild Selected FLW Scope' : '',
        'importModePolicy' => s8_is_rebuild_mode($importmode)
            ? flw_import_mode_policy_text($single_direct_import, $importmode, true)
            : ($single_direct_import
                ? 'S6 dry run resolves the canonical Stage Course, Unit Section, and Unit SCORM action without changing Moodle.'
                : 'S7 mapping preview resolves World+Stage Courses and Unit Sections without changing Moodle. Package-aware SCORM action is calculated by Batch Deploy with Dry run only.'),
        'batchStatusContract' => [
            'job' => ['PENDING', 'PREFLIGHT', 'RUNNING', 'CANCELLING', 'CANCELLED', 'SUCCEEDED', 'SUCCEEDED_WITH_WARNINGS', 'PARTIAL', 'FAILED', 'RESUMABLE'],
            'unit' => ['PENDING', 'RUNNING', 'CREATED', 'UPDATED', 'SUPERSEDED', 'UNCHANGED', 'SKIPPED', 'BLOCKED', 'CONFLICT', 'FAILED'],
        ],
        'batchPlanId' => $manifest['batchPlanId'] ?? '',
        'stageGroups' => $manifest['stageGroups'] ?? [],
        'catalogValidation' => $manifest['catalogValidation'] ?? null,
        'requestContract' => s6_single_import_request_contract($manifest, $importmode),
        'previewStateHash' => $previewstatehash,
        'singleImport' => $singleimportsummary,
        'destructivePathGuard' => [
            'singleOverwriteClearsStageCourse' => false,
            'clear_course_for_overwrite_reachable' => false,
            'clear_courses_above_id_reachable' => false,
            'reset_course_id_sequence_reachable' => false,
            'delete_course_reachable' => false,
            'course_delete_module_reachable_for_manual_content' => false,
            'legacyDestructiveHelpers' => 'isolated_legacy_development_only',
        ],
        'manifestPath' => $manifestpath,
        'moodleUrl' => rtrim((string)$CFG->wwwroot, '/'),
        'timestamp' => $stamp,
        'stageCourseMapPath' => $map_path,
        'unitSectionMapPath' => $section_map_path,
        'unitScormMapPath' => $scorm_map_path,
        'markerMethod' => 'COURSE_SECTION_SUMMARY_HTML_COMMENT',
        'scormIdentityMethod' => 'stable cmidnumber + UnitSCORMActivityID + SCORM manifest/SCO identifiers',
        'forceSupersede' => $force_supersede,
        'clearOperation' => $clearoperation,
        'results' => $results,
        'unitResults' => $unitresults,
        'orderMoves' => $order_moves,
        'summary' => $summary,
    ];
}

global $argv, $DB, $USER, $PAGE, $CFG;

$manifestpath = cli_value($argv, 'manifest');
if (!$manifestpath) {
    fwrite(STDERR, "Usage: php import_scorm_pilot_to_moodle.php --manifest=<pilot_manifest.json> [--config=<moodle/config.php>] [--courseid=124] [--sectionname=...] [--report=...] [--name-prefix=...] [--moodle-url=...] [--import-mode=overwrite|add_new|clear_add] [--stage-course-map=...] [--unit-section-map=...] [--unit-scorm-map=...] [--force-supersede] [--expect-preview-state=sha256] [--as-username=...] [--dry-run]\n");
    exit(1);
}
$courseid = (int)cli_value($argv, 'courseid', '124');
$dryrun = cli_flag($argv, 'dry-run');
$bylanguage = cli_flag($argv, 'by-language');
$previewcourses = cli_flag($argv, 'preview-courses');
$reportpatharg = cli_value($argv, 'report', '');
$nameprefix = cli_value($argv, 'name-prefix', 'SCORM Pilot') ?: 'SCORM Pilot';
$importmode = normalize_import_mode(cli_value($argv, 'import-mode', 'overwrite'));
$stagecoursemappath = stage_course_map_path(cli_value($argv, 'stage-course-map', ''));
$unitsectionmappath = unit_section_map_path(cli_value($argv, 'unit-section-map', ''));
$unitscormmappath = unit_scorm_map_path(cli_value($argv, 'unit-scorm-map', ''));
$forcesupersede = cli_flag($argv, 'force-supersede');
$expectedpreviewstate = trim((string)cli_value($argv, 'expect-preview-state', ''));
$asusername = trim((string)cli_value($argv, 'as-username', ''));
$moodleurl = clean_moodle_url(cli_value($argv, 'moodle-url', ''));
if ($moodleurl !== '') {
    $previouswwwroot = rtrim((string)$CFG->wwwroot, '/');
    if ($previouswwwroot !== $moodleurl) {
        mtrace('[moodle_url] using ' . $moodleurl . ' for generated Moodle links; config.php wwwroot is ' . $previouswwwroot);
    }
    $CFG->wwwroot = $moodleurl;
}

$manifestjson = file_get_contents($manifestpath);
if ($manifestjson === false) {
    fwrite(STDERR, "Could not read manifest: {$manifestpath}\n");
    exit(1);
}
$manifest = json_decode($manifestjson, true);
if (!is_array($manifest)) {
    fwrite(STDERR, "Manifest JSON is invalid: {$manifestpath}\n");
    exit(1);
}

$actor = get_admin();
if ($asusername !== '') {
    $requested = $DB->get_record('user', ['username' => $asusername, 'deleted' => 0], '*', IGNORE_MISSING);
    if (!$requested) {
        fwrite(STDERR, "Moodle user was not found or is deleted: {$asusername}\n");
        exit(1);
    }
    $actor = $requested;
}
\core\session\manager::set_user($actor);
$USER = $actor;

$stamp = preg_replace('/[^0-9_]+/', '', (string)($manifest['timestamp'] ?? date('Ymd_His')));
if ($stamp === '') {
    $stamp = date('Ymd_His');
}
$sectionname = cli_value($argv, 'sectionname', 'SmartCourses SCORM Pilot ' . $stamp);

if ($previewcourses) {
    $report = preview_course_map($manifest, $manifestpath, $stamp, $importmode, $stagecoursemappath, $unitsectionmappath, $unitscormmappath, $forcesupersede);
    $reportpath = $reportpatharg ?: dirname($manifestpath) . DIRECTORY_SEPARATOR . 'course_preview_report.json';
    file_put_contents($reportpath, json_out($report));
    mtrace('[report] ' . $reportpath);
    echo json_out($report) . PHP_EOL;
    exit(($report['summary']['failed'] ?? $report['summary']['conflictCount'] ?? 0) === 0 ? 0 : 2);
}

if ($bylanguage) {
    if (!$dryrun && s8_is_rebuild_mode($importmode) && $expectedpreviewstate === '') {
        $report = [
            'kind' => 'smartcourses_unit_scorm_upsert',
            'mode' => 'safe_scoped_rebuild',
            's8RebuildMode' => true,
            'visibleOperationName' => 'Rebuild Selected FLW Scope',
            'importMode' => $importmode,
            'dryRun' => false,
            'status' => 'PREVIEW_REQUIRED',
            'publicStatus' => 'BLOCKED',
            'message' => 'PREVIEW_REQUIRED: Run a package-aware dry-run preview for Rebuild Selected FLW Scope before executing the real rebuild.',
            'summary' => [
                'failed' => 1,
                'publicStatus' => 'BLOCKED',
                'statusCounts' => ['PREVIEW_REQUIRED' => 1],
            ],
        ];
        $reportpath = $reportpatharg ?: dirname($manifestpath) . DIRECTORY_SEPARATOR . 'pilot_import_by_language_report.json';
        file_put_contents($reportpath, json_out($report));
        mtrace('[report] ' . $reportpath);
        echo json_out($report) . PHP_EOL;
        exit(2);
    }
    if (!$dryrun && $expectedpreviewstate !== '') {
        $previewreport = import_by_language($manifest, $manifestpath, $stamp, $sectionname, true, $nameprefix, $importmode, $stagecoursemappath, $unitsectionmappath, $unitscormmappath, $forcesupersede);
        if (($previewreport['previewStateHash'] ?? '') !== $expectedpreviewstate) {
            $report = [
                'kind' => 'smartcourses_unit_scorm_upsert',
                'mode' => 'single_unit_scorm_upsert',
                's6SingleImport' => s6_is_single_direct_import($manifest, $manifest['items'] ?? []),
                'importMode' => $importmode,
                'dryRun' => false,
                'status' => 'PREVIEW_STALE',
                'publicStatus' => 'BLOCKED',
                'message' => 'PREVIEW_STALE: Moodle destination changed after preview. Run Preview Moodle destination again before importing.',
                'expectedPreviewStateHash' => $expectedpreviewstate,
                'actualPreviewStateHash' => $previewreport['previewStateHash'] ?? '',
                'previewReport' => $previewreport,
                'summary' => [
                    'failed' => 1,
                    'publicStatus' => 'BLOCKED',
                    'statusCounts' => ['PREVIEW_STALE' => 1],
                ],
            ];
            $reportpath = $reportpatharg ?: dirname($manifestpath) . DIRECTORY_SEPARATOR . 'pilot_import_by_language_report.json';
            file_put_contents($reportpath, json_out($report));
            mtrace('[report] ' . $reportpath);
            echo json_out($report) . PHP_EOL;
            exit(2);
        }
    }
    $report = import_by_language($manifest, $manifestpath, $stamp, $sectionname, $dryrun, $nameprefix, $importmode, $stagecoursemappath, $unitsectionmappath, $unitscormmappath, $forcesupersede);
    $reportpath = $reportpatharg ?: dirname($manifestpath) . DIRECTORY_SEPARATOR . ($dryrun ? 'pilot_import_by_language_dry_run_report.json' : 'pilot_import_by_language_report.json');
    file_put_contents($reportpath, json_out($report));
    mtrace('[report] ' . $reportpath);
    echo json_out($report) . PHP_EOL;
    exit(($report['summary']['failed'] ?? 0) === 0 ? 0 : 2);
}

$course = $DB->get_record('course', ['id' => $courseid], '*', MUST_EXIST);
$PAGE->set_context(context_course::instance($course->id));
$PAGE->set_course($course);

$sectionnumarg = cli_value($argv, 'section');
if ($sectionnumarg !== null && $sectionnumarg !== '') {
    $sectionnum = max(0, (int)$sectionnumarg);
} else {
    $sectionnum = find_or_create_pilot_section($course, $sectionname, $dryrun);
}

$items = $manifest['items'] ?? [];
$results = [];
$failures = 0;
foreach ($items as $item) {
    try {
        $result = import_item($course, $sectionnum, $item, $stamp, $dryrun, $nameprefix);
        $results[] = $result;
        mtrace('[' . $result['status'] . '] ' . ($result['label'] ?? 'unit'));
    } catch (Throwable $e) {
        $failures++;
        $results[] = [
            'label' => $item['label'] ?? '',
            'status' => 'failed',
            'error' => $e->getMessage(),
            'class' => get_class($e),
        ];
        mtrace('[failed] ' . ($item['label'] ?? 'unit') . ': ' . $e->getMessage());
    }
}

$report = [
    'kind' => 'smartcourses_scorm_pilot_import',
    'dryRun' => $dryrun,
    'manifestPath' => $manifestpath,
    'moodleUrl' => rtrim((string)$CFG->wwwroot, '/'),
    'courseId' => $courseid,
    'courseFullname' => $course->fullname,
    'sectionNumber' => $sectionnum,
    'sectionName' => $sectionname,
    'timestamp' => $stamp,
    'results' => $results,
    'summary' => [
        'imported' => count(array_filter($results, fn($row) => ($row['status'] ?? '') === 'imported')),
        'alreadyExists' => count(array_filter($results, fn($row) => ($row['status'] ?? '') === 'already_exists')),
        'dryRunReady' => count(array_filter($results, fn($row) => ($row['status'] ?? '') === 'dry_run_ready')),
        'skipped' => count(array_filter($results, fn($row) => ($row['status'] ?? '') === 'skipped')),
        'failed' => $failures,
    ],
];

$reportpath = $reportpatharg ?: dirname($manifestpath) . DIRECTORY_SEPARATOR . ($dryrun ? 'pilot_import_dry_run_report.json' : 'pilot_import_report.json');
file_put_contents($reportpath, json_out($report));
mtrace('[report] ' . $reportpath);
echo json_out($report) . PHP_EOL;
exit($failures === 0 ? 0 : 2);
