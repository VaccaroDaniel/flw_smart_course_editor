<?php
define('CLI_SCRIPT', true);

$options = getopt('', ['moodle-config:', 'zip:']);
$configpath = $options['moodle-config'] ?? '';
if ($configpath === '' || !is_file($configpath)) {
    fwrite(STDERR, "Usage: php s2b_moodle_storage_probe.php --moodle-config=/path/to/config.php\n");
    exit(2);
}

require($configpath);
$CFG->preventfilelocking = true;

$result = [
    'status' => 'RUNNING',
    'moodleRelease' => $CFG->release ?? '',
    'dataroot' => $CFG->dataroot ?? '',
    'datarootWritable' => is_writable($CFG->dataroot ?? ''),
    'filedirWritable' => is_writable(($CFG->dataroot ?? '') . '/filedir'),
    'freeSpace' => disk_free_space($CFG->dataroot ?? '.') ?: 0,
];

try {
    global $DB;
    $admin = $DB->get_record('user', ['id' => 2, 'deleted' => 0], '*', MUST_EXIST);
    \core\session\manager::set_user($admin);
    $fs = get_file_storage();
    $context = context_user::instance($admin->id);
    $draftitemid = file_get_unused_draft_itemid();
    $record = [
        'contextid' => $context->id,
        'component' => 'user',
        'filearea' => 'draft',
        'itemid' => $draftitemid,
        'filepath' => '/',
        'filename' => 's2b-string-probe.txt',
    ];
    $file = $fs->create_file_from_string($record, 'S2B storage probe ' . time());
    $result['storedFileId'] = $file->get_id();
    $result['contentHash'] = $file->get_contenthash();
    $file->delete();
    if (!empty($options['zip'])) {
        $zippath = $options['zip'];
        if (!is_file($zippath)) {
            throw new RuntimeException('ZIP not found: ' . $zippath);
        }
        $zip = new ZipArchive();
        if ($zip->open($zippath) !== true) {
            throw new RuntimeException('Could not open ZIP: ' . $zippath);
        }
        $result['zip'] = $zippath;
        $result['zipEntriesTested'] = 0;
        $result['zipEntryFailures'] = [];
        for ($i = 0; $i < $zip->numFiles; $i++) {
            $stat = $zip->statIndex($i);
            $name = $stat['name'] ?? ('entry-' . $i);
            if (str_ends_with($name, '/')) {
                continue;
            }
            $content = $zip->getFromIndex($i);
            if ($content === false) {
                throw new RuntimeException('Could not read ZIP entry: ' . $name);
            }
            $entryrecord = [
                'contextid' => $context->id,
                'component' => 'user',
                'filearea' => 'draft',
                'itemid' => file_get_unused_draft_itemid(),
                'filepath' => '/',
                'filename' => 'entry-' . $i . '-' . preg_replace('/[^A-Za-z0-9._-]+/', '-', basename($name)),
            ];
            try {
                $entryfile = $fs->create_file_from_string($entryrecord, $content);
                $result['zipEntriesTested']++;
                $entryfile->delete();
            } catch (Throwable $entryerror) {
                $result['zipEntryFailures'][] = [
                    'index' => $i,
                    'name' => $name,
                    'size' => strlen($content),
                    'sha1' => sha1($content),
                    'error' => $entryerror->getMessage(),
                    'errorClass' => get_class($entryerror),
                    'errorFile' => $entryerror->getFile(),
                    'errorLine' => $entryerror->getLine(),
                ];
                break;
            }
        }
        $zip->close();
        if ($result['zipEntryFailures']) {
            throw new RuntimeException('At least one ZIP entry failed Moodle file-pool storage.');
        }
    }
    $result['status'] = 'PASS';
} catch (Throwable $e) {
    $result['status'] = 'FAIL';
    $result['error'] = $e->getMessage();
    $result['errorClass'] = get_class($e);
    $result['errorFile'] = $e->getFile();
    $result['errorLine'] = $e->getLine();
    $result['errorTrace'] = $e->getTraceAsString();
}

echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL;
exit($result['status'] === 'PASS' ? 0 : 1);
