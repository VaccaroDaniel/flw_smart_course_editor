<?php
define('CLI_SCRIPT', true);

$options = getopt('', ['moodle-config:', 'delete']);
$configpath = $options['moodle-config'] ?? '';
if ($configpath === '' || !is_file($configpath)) {
    fwrite(STDERR, "Usage: php s2b_moodle_temp_course_cleanup.php --moodle-config=/path/to/config.php [--delete]\n");
    exit(2);
}

require($configpath);
require_once($CFG->dirroot . '/course/lib.php');
$CFG->preventfilelocking = true;

$delete = array_key_exists('delete', $options);
$rows = $DB->get_records_sql(
    "SELECT id, fullname, shortname, visible
       FROM {course}
      WHERE shortname LIKE :prefix
      ORDER BY id",
    ['prefix' => 'FLW_S2B_TMP_%']
);

$result = [
    'delete' => $delete,
    'found' => [],
    'deleted' => [],
    'errors' => [],
];

foreach ($rows as $course) {
    $item = [
        'id' => (int)$course->id,
        'shortname' => $course->shortname,
        'fullname' => $course->fullname,
        'visible' => (int)$course->visible,
    ];
    $result['found'][] = $item;
    if ($delete) {
        try {
            delete_course((int)$course->id, false);
            $result['deleted'][] = $item;
        } catch (Throwable $e) {
            $result['errors'][] = [
                'course' => $item,
                'error' => $e->getMessage(),
            ];
        }
    }
}

echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL;
exit($result['errors'] ? 1 : 0);
