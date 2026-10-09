from mcp_blender.server import _call_tool_result_from_blender

def test_failed_blender_envelope_becomes_mcp_error():
    result=_call_tool_result_from_blender({"ok": False, "error": {"code":"bad_input", "message":"nope", "details":{}}})
    assert result.is_error is True
    assert "bad_input" in result.content[0].text

def test_success_blender_envelope_is_not_mcp_error():
    result=_call_tool_result_from_blender({"ok": True, "result": {"value": 3}})
    assert not bool(result.is_error)