<?php
// Delete disposable S2B browser-player fixture course/user by exact IDs.

define('CLI_SCRIPT', true);

$options = getopt('', ['moodle-config:', 'course-id:', 'user-id:']);
$configpath = $options['moodle-config'] ?? '';
$courseid = (int)($options['course-id'] ?? 0);
$userid = (int)($options['user-id'] ?? 0);

if ($configpath === '' || !is_file($configpath) || !$courseid || !$userid) {
    fwrite(STDERR, "Usage: php s2b_moodle_browser_cleanup.php --moodle-config=/path/to/config.php --course-id=ID --user-id=ID\n");
    exit(2);
}

require($configpath);
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/user/lib.php');

global $DB;
$CFG->preventfilelocking = true;

$result = [
    'status' => 'RUNNING',
    'courseId' => $courseid,
    'userId' => $userid,
    'courseDeleted' => false,
    'userDeleted' => false,
    'errors' => [],
];

try {
    $course = $DB->get_record('course', ['id' => $courseid], 'id,shortname,fullname', IGNORE_MISSING);
    if (!$course) {
        $result['courseDeleted'] = true;
    } else {
        if (!str_starts_with($course->shortname, 'FLW_S2B_BROWSER_TMP_')) {
            s2b_cleanup_fail('Refusing to delete course without S2B browser temp prefix: ' . $course->shortname);
        }
        $coursebinwasenabled = get_config('tool_recyclebin', 'coursebinenable');
        $categorybinwasenabled = get_config('tool_recyclebin', 'categorybinenable');
        set_config('coursebinenable', 0, 'tool_recyclebin');
        set_config('categorybinenable', 0, 'tool_recyclebin');
        try {
            delete_course($courseid, false);
        } finally {
            if ($coursebinwasenabled !== false) {
                set_config('coursebinenable', $coursebinwasenabled, 'tool_recyclebin');
            }
            if ($categorybinwasenabled !== false) {
                set_config('categorybinenable', $categorybinwasenabled, 'tool_recyclebin');
            }
        }
        $result['courseDeleted'] = true;
    }
} catch (Throwable $e) {
    $result['errors'][] = 'course: ' . $e->getMessage();
}

try {
    $user = $DB->get_record('user', ['id' => $userid], '*', IGNORE_MISSING);
    if (!$user || (int)$user->deleted === 1) {
        $result['userDeleted'] = true;
    } else {
        if (!str_starts_with($user->username, 's2b_browser_')) {
            s2b_cleanup_fail('Refusing to delete user without S2B browser temp prefix: ' . $user->username);
        }
        delete_user($user);
        $result['userDeleted'] = true;
    }
} catch (Throwable $e) {
    $result['errors'][] = 'user: ' . $e->getMessage();
}

$result['status'] = $result['errors'] ? 'FAIL' : 'PASS';
echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . PHP_EOL;
exit($result['status'] === 'PASS' ? 0 : 1);

function s2b_cleanup_fail(string $message): void {
    throw new RuntimeException($message);
}
