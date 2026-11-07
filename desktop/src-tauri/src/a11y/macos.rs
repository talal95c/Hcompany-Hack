use super::{platform::*, *};
use accessibility_sys::*;
use accessibility_sys::{
    kAXErrorAttributeUnsupported as AX_UNSUPPORTED, kAXErrorCannotComplete as AX_TIMEOUT,
    kAXErrorInvalidUIElement as AX_INVALID, kAXErrorNoValue as AX_NO_VALUE,
    kAXErrorSuccess as AX_SUCCESS,
};
use core_foundation::{
    array::{CFArrayGetCount, CFArrayGetTypeID, CFArrayGetValueAtIndex},
    base::{CFGetTypeID, CFType, CFTypeRef, TCFType},
    boolean::CFBoolean,
    number::CFNumber,
    string::CFString,
};

#[derive(Default)]
pub struct Sensor {
    worker: Worker<Context>,
}
#[derive(Default)]
struct Context {
    objects: Registry<CFType>,
    screens: Vec<crate::coordinates::Monitor>,
}

fn status(code: AXError) -> Result<(), Error> {
    match code {
        AX_SUCCESS => Ok(()),
        AX_TIMEOUT => Err(Error::Timeout),
        AX_INVALID => Err(Error::StaleRef),
        _ => Err(Error::PermissionDenied),
    }
}
fn trusted() -> Result<(), Error> {
    if unsafe { AXIsProcessTrusted() } {
        Ok(())
    } else {
        Err(Error::PermissionDenied)
    }
}
fn element(value: &CFType) -> Result<AXUIElementRef, Error> {
    if unsafe { CFGetTypeID(value.as_CFTypeRef()) } != unsafe { AXUIElementGetTypeID() } {
        return Err(Error::StaleRef);
    }
    Ok(value.as_CFTypeRef() as AXUIElementRef)
}
fn prepare(value: &CFType, deadline: Instant) -> Result<AXUIElementRef, Error> {
    let remaining = deadline
        .checked_duration_since(Instant::now())
        .ok_or(Error::Timeout)?;
    let element = element(value)?;
    status(unsafe {
        AXUIElementSetMessagingTimeout(element, remaining.as_secs_f32().clamp(0.001, 0.15))
    })?;
    Ok(element)
}
fn copy(value: &CFType, key: &str, deadline: Instant) -> Result<Option<CFType>, Error> {
    let value = prepare(value, deadline)?;
    let key = CFString::new(key);
    let mut result: CFTypeRef = std::ptr::null();
    let code =
        unsafe { AXUIElementCopyAttributeValue(value, key.as_concrete_TypeRef(), &mut result) };
    if matches!(code, AX_UNSUPPORTED | AX_NO_VALUE) {
        return Ok(None);
    }
    status(code)?;
    if result.is_null() {
        return Ok(None);
    }
    Ok(Some(unsafe { CFType::wrap_under_create_rule(result) }))
}
fn scalar(value: &CFType) -> Option<String> {
    if value.instance_of::<CFString>() {
        Some(unsafe { CFString::wrap_under_get_rule(value.as_CFTypeRef() as _) }.to_string())
    } else if value.instance_of::<CFNumber>() {
        unsafe { CFNumber::wrap_under_get_rule(value.as_CFTypeRef() as _) }
            .to_f64()
            .filter(|v| v.is_finite())
            .map(|v| v.to_string())
    } else {
        None
    }
}
fn text(value: &CFType, key: &str, deadline: Instant) -> Result<String, Error> {
    Ok(copy(value, key, deadline)?
        .as_ref()
        .and_then(scalar)
        .unwrap_or_default())
}
fn boolean(value: &CFType, key: &str, deadline: Instant) -> Result<bool, Error> {
    Ok(copy(value, key, deadline)?.is_some_and(|v| {
        v.instance_of::<CFBoolean>()
            && unsafe { CFBoolean::wrap_under_get_rule(v.as_CFTypeRef() as _) }.into()
    }))
}
fn pair(
    value: &CFType,
    key: &str,
    kind: u32,
    deadline: Instant,
) -> Result<Option<[f64; 2]>, Error> {
    let mut pair = [0.; 2];
    if let Some(v) = copy(value, key, deadline)? {
        let ptr = v.as_CFTypeRef() as AXValueRef;
        if unsafe { CFGetTypeID(v.as_CFTypeRef()) } == unsafe { AXValueGetTypeID() }
            && unsafe { AXValueGetType(ptr) } == kind
        {
            if !unsafe { AXValueGetValue(ptr, kind, pair.as_mut_ptr().cast()) } {
                return Err(Error::PermissionDenied);
            }
            return Ok(Some(pair));
        }
    }
    Ok(None)
}
fn count(value: &CFType, key: &str, deadline: Instant) -> Result<Option<usize>, Error> {
    let value = prepare(value, deadline)?;
    let key = CFString::new(key);
    let mut count = 0;
    let code =
        unsafe { AXUIElementGetAttributeValueCount(value, key.as_concrete_TypeRef(), &mut count) };
    if matches!(code, AX_UNSUPPORTED | AX_NO_VALUE) {
        return Ok(None);
    }
    status(code)?;
    Ok(Some(count.max(0) as usize))
}
fn set(
    value: &CFType,
    key: &str,
    new: &CFType,
    deadline: Instant,
    check: &input::Authorization,
) -> Result<(), Error> {
    let element = prepare(value, deadline)?;
    let key = CFString::new(key);
    check().map_err(Error::guard)?;
    status(unsafe {
        AXUIElementSetAttributeValue(element, key.as_concrete_TypeRef(), new.as_CFTypeRef())
    })
}
impl Context {
    fn new() -> Result<Self, Error> {
        Ok(Self::default())
    }
    fn screens(&mut self) -> Result<(), Error> {
        self.screens = crate::native::monitors().map_err(|_| Error::PermissionDenied)?;
        Ok(())
    }
    fn resolve(&self, handle: &Handle) -> Result<CFType, Error> {
        trusted()?;
        if handle.path != "app" {
            return self.objects.get(handle);
        }
        let pid = handle.bus.parse::<i32>().map_err(|_| Error::StaleRef)?;
        if pid <= 0 {
            return Err(Error::StaleRef);
        }
        let ptr = unsafe { AXUIElementCreateApplication(pid) };
        if ptr.is_null() {
            return Err(Error::AppNotFound);
        }
        Ok(unsafe { CFType::wrap_under_create_rule(ptr.cast()) })
    }
    fn read(
        &mut self,
        handle: &Handle,
        children: bool,
        deadline: Instant,
    ) -> Result<Observation, Error> {
        let value = self.resolve(handle)?;
        let role = text(&value, "AXRole", deadline)?;
        let subrole = text(&value, "AXSubrole", deadline)?;
        let secure = secure_field(&role, &subrole, false);
        let normalized = ax_role(&role, &subrole).to_owned();
        let position = pair(&value, "AXPosition", kAXValueTypeCGPoint, deadline)?;
        let size = pair(&value, "AXSize", kAXValueTypeCGSize, deadline)?;
        let logical = position
            .zip(size)
            .map(|(position, size)| crate::coordinates::Rect {
                x: position[0],
                y: position[1],
                width: size[0],
                height: size[1],
            });
        let bounds =
            logical.and_then(|logical| crate::coordinates::ax_rect(&self.screens, logical));
        let visible = !boolean(&value, "AXHidden", deadline)?
            && !boolean(&value, "AXMinimized", deadline)?
            && (logical.is_none_or(|r| !r.valid()) || bounds.is_some());
        let mut node = Node {
            reference: String::new(),
            role: normalized,
            name: text(&value, "AXTitle", deadline)?,
            value: None,
            secure,
            states: vec![],
            bounds: bounds
                .map(|r| Bounds {
                    x: r.x,
                    y: r.y,
                    w: r.width,
                    h: r.height,
                })
                .unwrap_or(Bounds {
                    x: 0.,
                    y: 0.,
                    w: 0.,
                    h: 0.,
                }),
            parent_ref: None,
        };
        if node.name.is_empty() {
            node.name = text(&value, "AXDescription", deadline)?;
        }
        if visible {
            for (key, state) in [
                ("AXFocused", "focused"),
                ("AXSelected", "selected"),
                ("AXEnabled", "enabled"),
                ("AXExpanded", "expanded"),
            ] {
                if boolean(&value, key, deadline)? {
                    node.states.push(state.into());
                }
            }
            node.states.push("visible".into());
            if !secure {
                node.value = copy(&value, "AXValue", deadline)?.as_ref().and_then(scalar);
                node.secure = secure_field(&role, &text(&value, "AXSubrole", deadline)?, false);
                node.protect();
                if !node.secure {
                    let element = prepare(&value, deadline)?;
                    let key = CFString::new("AXValue");
                    let mut settable = 0;
                    let code = unsafe {
                        AXUIElementIsAttributeSettable(
                            element,
                            key.as_concrete_TypeRef(),
                            &mut settable,
                        )
                    };
                    if code == AX_SUCCESS && settable != 0 {
                        node.states.push("editable".into());
                    } else if code == AX_TIMEOUT {
                        return Err(Error::Timeout);
                    }
                }
            }
            if matches!(
                node.role.as_str(),
                "check_box" | "radio_button" | "toggle_button"
            ) && node.value.as_deref() == Some("1")
            {
                node.states.push("checked".into());
            }
        }
        let mut result = Observation {
            node,
            visible,
            children: vec![],
            reasons: vec![],
        };
        if !visible {
            return Ok(result);
        }
        let mut attribute = "AXChildren";
        let mut total = count(&value, attribute, deadline)?.unwrap_or(0);
        if total > 512 {
            let mut found = false;
            for candidate in ["AXVisibleRows", "AXVisibleChildren"] {
                if let Some(n) = count(&value, candidate, deadline)? {
                    attribute = candidate;
                    total = n;
                    found = true;
                    break;
                }
            }
            if !found {
                result.reasons.push(Reason::LargeContainerSkipped);
                return Ok(result);
            }
        }
        if !children {
            if total > 0 {
                result.reasons.push(Reason::DepthLimit);
            }
            return Ok(result);
        }
        if total > 2000 {
            result.reasons.push(Reason::NodeCap);
        }
        if total == 0 {
            return Ok(result);
        }
        let ax_element = prepare(&value, deadline)?;
        let key = CFString::new(attribute);
        let mut array = std::ptr::null();
        status(unsafe {
            AXUIElementCopyAttributeValues(
                ax_element,
                key.as_concrete_TypeRef(),
                0,
                total.min(2000) as _,
                &mut array,
            )
        })?;
        if array.is_null() {
            return Err(Error::PermissionDenied);
        }
        let owned = unsafe { CFType::wrap_under_create_rule(array.cast()) };
        if unsafe { CFGetTypeID(owned.as_CFTypeRef()) } != unsafe { CFArrayGetTypeID() } {
            return Err(Error::PermissionDenied);
        }
        let pid = handle.bus.parse().map_err(|_| Error::StaleRef)?;
        for index in 0..unsafe { CFArrayGetCount(array) } {
            let ptr = unsafe { CFArrayGetValueAtIndex(array, index) };
            if !ptr.is_null() {
                let child = unsafe { CFType::wrap_under_get_rule(ptr) };
                if element(&child).is_ok() {
                    result.children.push(self.objects.insert(pid, child));
                } else {
                    result.reasons.push(Reason::ChildReadError);
                }
            } else {
                result.reasons.push(Reason::ChildReadError);
            }
        }
        Ok(result)
    }
    fn action(
        &mut self,
        handle: Handle,
        action: String,
        value: Option<String>,
        check: input::Authorization,
    ) -> Result<(), Error> {
        let deadline = Instant::now() + Duration::from_secs(2);
        trusted()?;
        let element = self.resolve(&handle)?;
        let role = text(&element, "AXRole", deadline)?;
        let subrole = text(&element, "AXSubrole", deadline)?;
        if action == "set_value" && secure_field(&role, &subrole, false) {
            return Err(Error::PermissionDenied);
        }
        match action.as_str() {
            "focus" => set(
                &element,
                "AXFocused",
                &CFBoolean::true_value().as_CFType(),
                deadline,
                &check,
            ),
            "select" => set(
                &element,
                "AXSelected",
                &CFBoolean::true_value().as_CFType(),
                deadline,
                &check,
            ),
            "expand" | "collapse" => {
                if copy(&element, "AXExpanded", deadline)?.is_some() {
                    set(
                        &element,
                        "AXExpanded",
                        &CFBoolean::from(action == "expand").as_CFType(),
                        deadline,
                        &check,
                    )
                } else {
                    self.perform(
                        &element,
                        if action == "expand"
                            && matches!(role.as_str(), "AXMenu" | "AXPopUpButton" | "AXComboBox")
                        {
                            "AXShowMenu"
                        } else if action == "expand" {
                            "AXExpand"
                        } else {
                            "AXCollapse"
                        },
                        deadline,
                        &check,
                    )
                }
            }
            "set_value" => {
                let text = value.ok_or(Error::PermissionDenied)?;
                let old = copy(&element, "AXValue", deadline)?;
                let new = if old.is_some_and(|v| v.instance_of::<CFNumber>()) {
                    CFNumber::from(
                        text.parse::<f64>()
                            .ok()
                            .filter(|v| v.is_finite())
                            .ok_or(Error::PermissionDenied)?,
                    )
                    .as_CFType()
                } else {
                    CFString::new(&text).as_CFType()
                };
                set(&element, "AXValue", &new, deadline, &check)
            }
            "press" | "toggle" => self.perform(&element, "AXPress", deadline, &check),
            "scroll_into_view" => self.perform(&element, "AXScrollToVisible", deadline, &check),
            _ => Err(Error::PermissionDenied),
        }
    }
    fn perform(
        &self,
        value: &CFType,
        action: &str,
        deadline: Instant,
        check: &input::Authorization,
    ) -> Result<(), Error> {
        let element = prepare(value, deadline)?;
        let action = CFString::new(action);
        check().map_err(Error::guard)?;
        status(unsafe { AXUIElementPerformAction(element, action.as_concrete_TypeRef()) })
    }
}
#[derive(Deserialize)]
struct NativeApp {
    app_id: String,
    name: String,
    executable: String,
    pid: u32,
    focused: bool,
}
impl AccessibilitySensor for Sensor {
    fn apps(&self) -> Task<'_, Vec<App>> {
        Box::pin(self.worker.call(Context::new, |_| {
            trusted()?;
            let bytes = crate::native::mac_call(&["apps"]).map_err(|_| Error::PermissionDenied)?;
            let apps: Vec<NativeApp> =
                serde_json::from_slice(&bytes).map_err(|_| Error::PermissionDenied)?;
            Ok(apps
                .into_iter()
                .filter(|a| a.pid != std::process::id())
                .map(|a| App {
                    app_id: a.app_id,
                    name: a.name,
                    executable: a.executable,
                    pid: a.pid,
                    focused: a.focused,
                    handle: Handle {
                        bus: a.pid.to_string(),
                        path: "app".into(),
                    },
                })
                .collect())
        }))
    }
    fn snapshot<'a>(&'a self, root: &'a Handle, depth: usize, deadline: Instant) -> Task<'a, Tree> {
        let root = root.clone();
        Box::pin(self.worker.call(Context::new, move |c| {
            c.screens()?;
            walk(root, depth, deadline, |h, children, deadline| {
                c.read(h, children, deadline)
            })
        }))
    }
    fn refresh<'a>(&'a self, handle: &'a Handle) -> Task<'a, Node> {
        let handle = handle.clone();
        Box::pin(self.worker.call(Context::new, move |c| {
            c.screens()?;
            let observation = c.read(&handle, false, Instant::now() + Duration::from_secs(2))?;
            if !valid_bounds(observation.node.bounds) || !observation.visible {
                return Err(Error::StaleRef);
            }
            Ok(observation.node)
        }))
    }
    fn action<'a>(
        &'a self,
        handle: &'a Handle,
        action: &'a str,
        value: Option<&'a str>,
        guard: &'a input::ActionGuard<'a>,
    ) -> Task<'a, ()> {
        let (handle, action, value) = (handle.clone(), action.to_owned(), value.map(str::to_owned));
        Box::pin(self.worker.action(Context::new, guard, move |c, check| {
            c.action(handle, action, value, check)
        }))
    }
}
