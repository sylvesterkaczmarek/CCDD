"""Compile the complete source and exercise real CSV extraction on exact commits."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

SOURCE = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads(Path(__file__).with_name("case.json").read_text())
assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip() == CFG["source"]
print("TESTED SOURCE", CFG["source"], flush=True)
LIBS = OUT / "test-libs"
LIBS.mkdir(exist_ok=True)
DEPENDENCIES = [
    "junit/junit/4.13.2/junit-4.13.2.jar",
    "org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar",
    "org/mockito/mockito-core/4.11.0/mockito-core-4.11.0.jar",
    "net/bytebuddy/byte-buddy/1.12.19/byte-buddy-1.12.19.jar",
    "net/bytebuddy/byte-buddy-agent/1.12.19/byte-buddy-agent-1.12.19.jar",
    "org/objenesis/objenesis/3.3/objenesis-3.3.jar",
]
for path in DEPENDENCIES:
    urllib.request.urlretrieve("https://repo.maven.apache.org/maven2/" + path, LIBS / path.rsplit("/", 1)[-1])
CLASSES = OUT / "classes"
CLASSES.mkdir(exist_ok=True)
CP = os.pathsep.join(map(str, [CLASSES, SOURCE / "CCDD_lib/commons-io-2.6.jar", SOURCE / "CCDD_lib/*", LIBS / "*"]))
EXPORTS = [] if os.environ["TEST_JAVA"] == "8" else ["--add-exports", "java.desktop/sun.swing=ALL-UNNAMED"]
PRODUCTION = SOURCE / "src/CCDD/CcddCSVHandler.java"
FIXED = PRODUCTION.read_bytes()
RESULTS = {}

def run(label, command, expected=0):
    p = subprocess.run(command, cwd=SOURCE, capture_output=True, text=True, timeout=180)
    output = p.stdout + p.stderr
    (OUT / (label + ".log")).write_text(output)
    print(label, "exit", p.returncode, output[-450:], flush=True)
    assert p.returncode == expected, (label, p.returncode, output[-6000:])
    return output

def compile_changed(label):
    run(label, ["javac", "-encoding", "UTF-8", "-cp", CP, "-d", str(CLASSES), str(PRODUCTION)])

def test(label, failures=0):
    out = run(label, ["java", "-Djava.awt.headless=true", *EXPORTS, "-cp", CP,
                      "org.junit.runner.JUnitCore", "CCDD.CcddCSVDataTest"], int(bool(failures)))
    if failures:
        assert f"Tests run: 90,  Failures: {failures}" in out, out
    else:
        assert "OK (90 tests)" in out, out
    RESULTS[label] = {"tests": 90, "failures": failures}

run("java-version", ["java", "-version"])
paths = sorted((SOURCE / "src").rglob("*.java"))
assert len(paths) == 103, len(paths)
argfile = OUT / "sources.txt"
argfile.write_text("\n".join(str(p) for p in paths + [SOURCE / "tests/CCDD/CcddCSVDataTest.java"]))
run("compile-all", ["javac", "-encoding", "UTF-8", *EXPORTS, "-cp", CP, "-d", str(CLASSES), "@" + str(argfile)])
test("fixed")
try:
    PRODUCTION.write_bytes(subprocess.check_output(["git", "show", CFG["base"] + ":src/CCDD/CcddCSVHandler.java"], cwd=SOURCE))
    compile_changed("compile-original")
    test("original", 45)
    before, after = FIXED.decode().split("                // Next tag found", 1)
    after, count = re.subn(r"(CSVTags\.[A-Z_]+\.getTag\(\))\.equals\(searchKey\)", r"searchKey == \1", after)
    assert count == 4, count
    PRODUCTION.write_text(before + "                // Next tag found" + after)
    compile_changed("compile-partial-fix")
    test("partial-fix", 16)
finally:
    PRODUCTION.write_bytes(FIXED)
compile_changed("compile-restored")
test("restored")
run("source-restoration", ["git", "diff", "--exit-code"])
run("patch-check", ["git", "diff", "--check", CFG["base"], "HEAD"])
(OUT / "results.json").write_text(json.dumps(RESULTS, indent=2))
print("VALIDATION COMPLETE", CFG["source"], flush=True)
