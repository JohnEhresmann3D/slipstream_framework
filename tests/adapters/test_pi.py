from __future__ import annotations

from pathlib import Path

from slipstream.loop.backends.base import AgentRequest
from slipstream.loop.backends.pi import PiBackend, PiConfig


def _fake_pi(tmp_path: Path) -> Path:
    script = tmp_path / "fake_pi.py"
    script.write_text(
        """#!/usr/bin/env python3
import json, sys
session_id = 'pi-session-id'
session_file = '/tmp/pi-session.jsonl'
prompt_count = 0
for raw in sys.stdin:
    cmd = json.loads(raw)
    t = cmd.get('type')
    if t == 'switch_session':
        session_file = cmd.get('sessionPath')
        print(json.dumps({'type':'response','command':'switch_session','id':cmd.get('id'),'success':True,'data':{'cancelled':False}}), flush=True)
    elif t == 'prompt':
        prompt_count += 1
        print(json.dumps({'type':'response','command':'prompt','id':cmd.get('id'),'success':True}), flush=True)
        print(json.dumps({'type':'message_update','assistantMessageEvent':{'type':'text_delta','delta':'hello '}}), flush=True)
        print(json.dumps({'type':'message_update','assistantMessageEvent':{'type':'text_delta','delta':'world'}}), flush=True)
        print(json.dumps({'type':'agent_settled'}), flush=True)
    elif t == 'get_state':
        print(json.dumps({'type':'response','command':'get_state','id':cmd.get('id'),'success':True,'data':{'sessionId':session_id,'sessionFile':session_file}}), flush=True)
    elif t == 'get_session_stats':
        print(json.dumps({'type':'response','command':'get_session_stats','id':cmd.get('id'),'success':True,'data':{'sessionId':session_id,'sessionFile':session_file,'cost':0.12 * prompt_count,'tokens':{'input':20 * prompt_count,'output':5 * prompt_count}}}), flush=True)
    elif t == 'abort':
        print(json.dumps({'type':'response','command':'abort','id':cmd.get('id'),'success':True}), flush=True)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_pi_rpc_adapter_normalizes_session_usage_and_text(tmp_path):
    exe = _fake_pi(tmp_path)
    backend = PiBackend(PiConfig(executable=str(exe)))
    try:
        result = backend.run(AgentRequest(prompt="hello", workspace=tmp_path))
        assert result.text == "hello world"
        # Pi continuation uses its durable session file as the protocol's opaque
        # session handle. This can survive a Slipstream process restart.
        assert result.session_id == "/tmp/pi-session.jsonl"
        assert result.cost_usd == 0.12
        assert result.input_tokens == 20
        assert result.output_tokens == 5

        second = backend.run(AgentRequest(prompt="again", workspace=tmp_path, session_id=result.session_id))
        assert second.session_id == "/tmp/pi-session.jsonl"
        assert second.cost_usd == 0.12
    finally:
        backend.close()


def test_pi_resume_switches_by_session_file_after_process_restart(tmp_path):
    exe = _fake_pi(tmp_path)
    backend = PiBackend(PiConfig(executable=str(exe)))
    try:
        result = backend.run(AgentRequest(prompt="hello", workspace=tmp_path))
        backend.close()
        resumed = backend.run(AgentRequest(prompt="resume", workspace=tmp_path, session_id=result.session_id))
        assert resumed.session_id == result.session_id
    finally:
        backend.close()


def test_pi_timeout_maps_to_backend_timeout(tmp_path):
    from slipstream.loop.backends.base import BackendTimeout

    script = tmp_path / "slow_pi.py"
    script.write_text(
        """#!/usr/bin/env python3
import json, sys, time
for raw in sys.stdin:
    cmd = json.loads(raw)
    if cmd.get('type') == 'get_session_stats':
        print(json.dumps({'type':'response','command':'get_session_stats','id':cmd.get('id'),'success':True,'data':{'cost':0,'tokens':{'input':0,'output':0}}}), flush=True)
    elif cmd.get('type') == 'prompt':
        time.sleep(5)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    backend = PiBackend(PiConfig(executable=str(script)))
    try:
        try:
            backend.run(AgentRequest(prompt="hang", workspace=tmp_path, timeout_sec=1))
        except BackendTimeout:
            pass
        else:
            raise AssertionError("Expected BackendTimeout")
    finally:
        backend.close()
