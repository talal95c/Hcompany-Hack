use std::sync::LazyLock;

use serde_json::{json, Value};

pub const MAX_MESSAGE: usize = 8 * 1024 * 1024;

static VALIDATOR: LazyLock<jsonschema::Validator> = LazyLock::new(|| {
    let mut schema: Value =
        serde_json::from_str(include_str!("../../../contracts/desktop-ws.schema.json")).unwrap();
    let mut commands: Value =
        serde_json::from_str(include_str!("../../../contracts/commands.schema.json")).unwrap();
    commands.as_object_mut().unwrap().remove("$id");
    for item in schema["oneOf"].as_array_mut().unwrap() {
        if item["properties"]["type"]["const"] == "command" {
            item["properties"]["payload"] = commands.clone();
        }
    }
    jsonschema::validator_for(&schema).expect("embedded protocol schema")
});

pub fn validate(value: &Value, session: &str) -> Result<(), String> {
    VALIDATOR.validate(value).map_err(|e| e.to_string())?;
    if value["session_id"] != session {
        return Err("session mismatch".into());
    }
    if value["type"] == "command" && value["payload"]["session_id"] != session {
        return Err("command session mismatch".into());
    }
    Ok(())
}

pub fn parse(text: &str, session: &str) -> Result<Value, String> {
    if text.len() > MAX_MESSAGE {
        return Err("message exceeds size limit".into());
    }
    let value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    validate(&value, session)?;
    Ok(value)
}

pub fn envelope(session: &str, kind: &str, payload: Value, reply: Option<&str>) -> Value {
    json!({"schema_version":"1.0", "session_id":session,
        "message_id":uuid::Uuid::new_v4().to_string(), "reply_to":reply,
        "type":kind, "payload":payload})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_contract_fixtures() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../contracts/examples/desktop-ws");
        for (folder, valid) in [("valid", true), ("invalid", false)] {
            for entry in std::fs::read_dir(root.join(folder)).unwrap() {
                let value: Value =
                    serde_json::from_str(&std::fs::read_to_string(entry.unwrap().path()).unwrap())
                        .unwrap();
                let session = value["session_id"].as_str().unwrap_or("");
                assert_eq!(validate(&value, session).is_ok(), valid, "{value}");
            }
        }
    }

    #[test]
    fn reject_wrong_session_and_corruption() {
        let ping = envelope("s1", "ping", json!({"nonce":"test"}), None);
        assert!(validate(&ping, "s2").is_err());
        assert!(parse("{}", "s1").is_err());
        assert!(parse("not json", "s1").is_err());
        assert!(parse(&" ".repeat(MAX_MESSAGE + 1), "s1").is_err());
    }
}
