#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
MAIN_PY="$ROOT_DIR/main.py"
OUT_DIR="$ROOT_DIR/output/sample_script"
STORYBOARD_JSON="$OUT_DIR/storyboard.json"
TIMELINE_JSON="$OUT_DIR/book_timeline.json"
COMPLIANCE_JSON="$OUT_DIR/compliance_report.json"
PACKET_JSON="$OUT_DIR/animator_instruction_packet.json"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  printf "PASS: %s\n" "$1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  printf "FAIL: %s\n" "$1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

run_cmd() {
  local name="$1"
  shift
  if "$@" >/tmp/phase2_check.out 2>/tmp/phase2_check.err; then
    pass "$name"
  else
    fail "$name"
    printf "  stdout: %s\n" "$(tr '\n' ' ' </tmp/phase2_check.out)"
    printf "  stderr: %s\n" "$(tr '\n' ' ' </tmp/phase2_check.err)"
  fi
}

check_python() {
  local name="$1"
  local code="$2"
  if "$PYTHON_BIN" - <<PY
$code
PY
  then
    pass "$name"
  else
    fail "$name"
  fi
}

echo "== Phase-2 Test Runner =="
echo "Root: $ROOT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python not found at $PYTHON_BIN"
  exit 1
fi

if [[ ! -f "$MAIN_PY" ]]; then
  echo "main.py not found at $MAIN_PY"
  exit 1
fi

echo
echo "== 1) CLI regression =="
run_cmd "batch run" "$PYTHON_BIN" "$MAIN_PY" batch --input-dir scripts
run_cmd "single script run" "$PYTHON_BIN" "$MAIN_PY" run --input scripts/sample_script.md
run_cmd "dual script run" "$PYTHON_BIN" "$MAIN_PY" run --input scripts/sample_script.md --academic-input scripts/sample_script.md

echo
echo "== 2) JSON feature checks =="

check_python "output files exist" "
from pathlib import Path
paths = [
  Path(r'$STORYBOARD_JSON'),
  Path(r'$TIMELINE_JSON'),
  Path(r'$COMPLIANCE_JSON'),
  Path(r'$PACKET_JSON'),
]
assert all(p.exists() for p in paths), [str(p) for p in paths if not p.exists()]
"

check_python "sentence index incremental" "
import json
d=json.load(open(r'$STORYBOARD_JSON'))
last=0
for sec in d['sections']:
  for para in sec['paragraphs']:
    for s in para['scenes']:
      assert s['sentence_index'] > last
      last = s['sentence_index']
"

check_python "dual sync fields present" "
import json
d=json.load(open(r'$STORYBOARD_JSON'))
assert d['sync_mode'] == 'dual_script'
for sec in d['sections']:
  for para in sec['paragraphs']:
    for s in para['scenes']:
      assert s.get('alignment_id')
      assert 'academic_sentence' in s
      assert 'alignment_confidence' in s
"

check_python "style prompt present in every image_prompt" "
import json
style='A detailed black-and-white charcoal rendering with subtle gradient transitions, executed in a classical artistic style with a muted palette and dramatic chiaroscuro lighting, medium shot.'
d=json.load(open(r'$STORYBOARD_JSON'))
for sec in d['sections']:
  for para in sec['paragraphs']:
    for s in para['scenes']:
      assert style in s['image_prompt']
"

check_python "scene durations <= 3 seconds" "
import json
sb=json.load(open(r'$STORYBOARD_JSON'))
for sec in sb['sections']:
  for para in sec['paragraphs']:
    for s in para['scenes']:
      assert s['scene_duration_sec'] <= 3.0
"

check_python "timeline durations <= 3 for sentence scenes" "
import json
bt=json.load(open(r'$TIMELINE_JSON'))
for sec in bt['sections']:
  for e in sec['events']:
    if e.get('event') == 'sentence_scene':
      assert e.get('duration_sec', 0) <= 3.0
"

check_python "zoom and sketch reveal intent set" "
import json
bt=json.load(open(r'$TIMELINE_JSON'))
for sec in bt['sections']:
  for e in sec['events']:
    if e.get('event') == 'sentence_scene':
      assert e.get('camera') == 'zoom in then zoom out'
      assert e.get('sketch_reveal') is True
"

check_python "section close and page flip set" "
import json
bt=json.load(open(r'$TIMELINE_JSON'))
for sec in bt['sections']:
  assert sec.get('section_close', {}).get('event') == 'full_page_reveal'
  assert sec.get('next_transition') == 'page_flip'
"

check_python "compliance report has expected checks" "
import json
c=json.load(open(r'$COMPLIANCE_JSON'))
checks=c['checks']
required=[
  'sentence_level_visuals',
  'scene_duration_max_3_sec',
  'charcoal_prompt_present_all_scenes',
  'book_timeline_required',
  'zoom_only_transition_intent',
  'section_close_full_page_reveal',
  'canva_only_mode_enabled',
  'dual_script_sync_present_when_provided',
  'footnote_references_per_sentence',
]
for key in required:
  assert key in checks
  assert checks[key] is True
"

check_python "animator packet required scene fields" "
import json
a=json.load(open(r'$PACKET_JSON'))
required=['main_text_to_display','placement','figures_animations_in_background','arrows_connections_needed','additional_notes']
for p in a['paragraph_templates']:
  for s in p['scenes']:
    for k in required:
      assert k in s
"

check_python "branding metadata in timeline" "
import json
b=json.load(open(r'$TIMELINE_JSON'))
assert b.get('brand') == 'Theology Academy'
logo = b.get('logo', {})
assert logo.get('variant') == 'globe_cross_no_shadow'
assert logo.get('languages') == 'english_arabic'
assert logo.get('shadow') == 'none'
"

echo
echo "== 3) Canva-only enforcement =="
if "$PYTHON_BIN" "$MAIN_PY" generate-images --storyboard "$STORYBOARD_JSON" >/tmp/phase2_canva.out 2>/tmp/phase2_canva.err; then
  fail "generate-images blocked in canva-only mode"
else
  if "$PYTHON_BIN" - <<PY
text = open('/tmp/phase2_canva.out', encoding='utf-8').read()
assert 'Canva-only mode is enabled' in text
PY
  then
    pass "generate-images blocked in canva-only mode"
  else
    fail "generate-images blocked in canva-only mode"
    printf "  output: %s\n" "$(tr '\n' ' ' </tmp/phase2_canva.out)"
  fi
fi

echo
echo "== 4) API negative tests (if server running) =="
if curl -sS -o /tmp/phase2_health.out -w "%{http_code}" "$BASE_URL/" >/tmp/phase2_health.code 2>/dev/null; then
  HTTP_CODE="$(cat /tmp/phase2_health.code)"
  if [[ "$HTTP_CODE" =~ ^2|3 ]]; then
    printf 'fake image' >/tmp/test_phase2.png
    CODE_400="$(curl -sS -o /tmp/phase2_png.out -w "%{http_code}" -X POST "$BASE_URL/process" -F "source_file=@/tmp/test_phase2.png")"
    [[ "$CODE_400" == "400" ]] && pass "unsupported upload returns 400" || fail "unsupported upload returns 400"

    CODE_404_JOB="$(curl -sS -o /tmp/phase2_job404.out -w "%{http_code}" "$BASE_URL/jobs/does_not_exist")"
    [[ "$CODE_404_JOB" == "404" ]] && pass "missing job returns 404" || fail "missing job returns 404"

    CODE_404_FILE="$(curl -sS -o /tmp/phase2_file404.out -w "%{http_code}" "$BASE_URL/files/sample_script/x.json")"
    [[ "$CODE_404_FILE" == "404" ]] && pass "missing file returns 404" || fail "missing file returns 404"
  else
    echo "Server not ready at $BASE_URL (code: $HTTP_CODE); skipping API tests."
  fi
else
  echo "Server not running at $BASE_URL; skipping API tests."
fi

echo
echo "== Summary =="
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi

exit 0
