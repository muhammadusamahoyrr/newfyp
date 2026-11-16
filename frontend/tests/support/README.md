# Why there is NO `--test-force-exit` (removed 2026-11-16)

From 2026-09-05 the suite ran with `--test-force-exit`, because
`mod_documents_dom.test.mjs` (React's scheduler + jsdom) kept timers alive and
the file never exited.

The flag was hiding a worse problem. It ends each test file's process the
moment its last test finishes. On Linux, a child's results travel to the runner
over a pipe that is written asynchronously, so the forced exit cut off results
still in flight: those tests were simply never counted -- not failed, not
skipped, just absent. GitHub Actions reported 1839, 1878 and 1892 tests on
different runs of unchanged code; the suite has 1940. Windows (where the suite
was usually run) did not show it.

By 2026-11-16 nothing needed the flag: the full suite, run without it, exits on
its own (1940 passed). If a file ever stops exiting again:

* fix the handle in that file (unmount, close the jsdom window, clear or
  `unref()` the timer) -- do not bring the flag back;
* until then it fails visibly: each test has a 2-minute limit
  (`--test-timeout=120000` in package.json) and the CI step a 20-minute one.
