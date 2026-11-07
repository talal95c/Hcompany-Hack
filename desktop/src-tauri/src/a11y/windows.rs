use super::{platform::*, *};
use ::windows::{
    core::Interface,
    Win32::{
        System::Com::{CoCreateInstance, CLSCTX_INPROC_SERVER},
        UI::Accessibility::{CUIAutomation8, IUIAutomation, IUIAutomation2},
    },
};
use uiautomation::{
    core::{UICacheRequest, UITreeWalker},
    patterns::*,
    types::UIProperty,
    UIAutomation, UIElement,
};
use windows_sys::Win32::System::Com::{CoInitializeEx, CoUninitialize, COINIT_MULTITHREADED};

#[derive(Default)]
pub struct Sensor {
    worker: Worker<Context>,
}
struct Com;
impl Drop for Com {
    fn drop(&mut self) {
        unsafe { CoUninitialize() }
    }
}
struct Context {
    automation: UIAutomation,
    native: IUIAutomation2,
    walker: UITreeWalker,
    cache: UICacheRequest,
    objects: Registry<UIElement>,
    _com: Com,
}
fn native_error(error: uiautomation::errors::Error) -> Error {
    match error.code() as u32 {
        0x80040201 => Error::StaleRef,
        0x80131505 | 2 => Error::Timeout,
        _ => Error::PermissionDenied,
    }
}
fn optional(result: uiautomation::Result<UIElement>) -> Result<Option<UIElement>, Error> {
    match result {
        Ok(element) => Ok(Some(element)),
        Err(error) if uia_end(error.code()) => Ok(None),
        Err(error) => Err(native_error(error)),
    }
}
impl Context {
    fn new() -> Result<Self, Error> {
        if unsafe { CoInitializeEx(std::ptr::null(), COINIT_MULTITHREADED as u32) } < 0 {
            return Err(Error::PermissionDenied);
        }
        let com = Com;
        let native: IUIAutomation2 =
            unsafe { CoCreateInstance(&CUIAutomation8, None, CLSCTX_INPROC_SERVER) }
                .map_err(|_| Error::PermissionDenied)?;
        let base: IUIAutomation = native.cast().map_err(|_| Error::PermissionDenied)?;
        let automation = UIAutomation::from(base);
        let walker = automation.get_control_view_walker().map_err(native_error)?;
        let cache = automation.create_cache_request().map_err(native_error)?;
        for property in [
            UIProperty::ControlType,
            UIProperty::Name,
            UIProperty::ProcessId,
            UIProperty::IsEnabled,
            UIProperty::HasKeyboardFocus,
            UIProperty::IsOffscreen,
            UIProperty::BoundingRectangle,
            UIProperty::IsPassword,
            UIProperty::ToggleToggleState,
            UIProperty::SelectionItemIsSelected,
            UIProperty::ExpandCollapseExpandCollapseState,
        ] {
            cache.add_property(property).map_err(native_error)?;
        }
        for pattern in [
            UIPatternType::Toggle,
            UIPatternType::SelectionItem,
            UIPatternType::ExpandCollapse,
        ] {
            cache.add_pattern(pattern).map_err(native_error)?;
        }
        Ok(Self {
            automation,
            native,
            walker,
            cache,
            objects: Registry::default(),
            _com: com,
        })
    }
    fn timeout(&self, deadline: Instant) -> Result<(), Error> {
        let millis = deadline
            .checked_duration_since(Instant::now())
            .ok_or(Error::Timeout)?
            .as_millis()
            .clamp(1, 200) as u32;
        unsafe {
            self.native
                .SetConnectionTimeout(millis)
                .and_then(|_| self.native.SetTransactionTimeout(millis))
        }
        .map_err(|_| Error::PermissionDenied)
    }
    fn resolve(&self, handle: &Handle, deadline: Instant) -> Result<UIElement, Error> {
        self.timeout(deadline)?;
        if handle.path != "app" {
            return self.objects.get(handle);
        }
        let pid = handle.bus.parse::<u32>().map_err(|_| Error::StaleRef)?;
        if let Ok(mut focused) = self.automation.get_focused_element() {
            if focused.get_process_id().map_err(native_error)? == pid {
                while let Ok(parent) = self.walker.get_parent(&focused) {
                    self.timeout(deadline)?;
                    if parent.get_process_id().map_err(native_error)? != pid {
                        break;
                    }
                    focused = parent;
                }
                return Ok(focused);
            }
        }
        let desktop = self.automation.get_root_element().map_err(native_error)?;
        let mut candidate = optional(self.walker.get_first_child(&desktop))?;
        while let Some(element) = candidate {
            self.timeout(deadline)?;
            if element.get_process_id().map_err(native_error)? == pid {
                return Ok(element);
            }
            candidate = optional(self.walker.get_next_sibling(&element))?;
        }
        Err(Error::AppNotFound)
    }
    fn read(
        &mut self,
        handle: &Handle,
        children: bool,
        deadline: Instant,
    ) -> Result<Observation, Error> {
        let original = self.resolve(handle, deadline)?;
        let element = original
            .build_updated_cache(&self.cache)
            .map_err(native_error)?;
        let secure = secure_field("", "", element.is_cached_password().map_err(native_error)?);
        let visible = !element.is_cached_offscreen().map_err(native_error)?;
        let toggle = element.get_cached_pattern::<UITogglePattern>().ok();
        let role = uia_role(
            element.get_cached_control_type().map_err(native_error)? as i32,
            toggle.is_some(),
        );
        let bounds = element
            .get_cached_bounding_rectangle()
            .map_err(native_error)?;
        let mut node = Node {
            reference: String::new(),
            role: role.into(),
            name: element.get_cached_name().map_err(native_error)?,
            value: None,
            secure,
            states: vec![],
            bounds: Bounds {
                x: bounds.get_left() as f64,
                y: bounds.get_top() as f64,
                w: bounds.get_width() as f64,
                h: bounds.get_height() as f64,
            },
            parent_ref: None,
        };
        if element.is_cached_enabled().map_err(native_error)? {
            node.states.push("enabled".into());
        }
        if element.has_cached_keyboard_focus().map_err(native_error)? {
            node.states.push("focused".into());
        }
        if toggle
            .and_then(|p| p.get_cached_toggle_state().ok())
            .is_some_and(|s| s as i32 == 1)
        {
            node.states.push("checked".into());
        }
        if element
            .get_cached_pattern::<UISelectionItemPattern>()
            .and_then(|p| p.is_cached_selected())
            .unwrap_or(false)
        {
            node.states.push("selected".into());
        }
        if element
            .get_cached_pattern::<UIExpandCollapsePattern>()
            .and_then(|p| p.get_cached_state())
            .is_ok_and(|s| s as i32 == 1)
        {
            node.states.push("expanded".into());
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
        result.node.states.push("visible".into());
        if !secure {
            self.timeout(deadline)?;
            let cache = self
                .automation
                .create_cache_request()
                .map_err(native_error)?;
            cache
                .add_pattern(UIPatternType::Value)
                .map_err(native_error)?;
            cache
                .add_property(UIProperty::ValueValue)
                .map_err(native_error)?;
            cache
                .add_property(UIProperty::IsPassword)
                .map_err(native_error)?;
            cache
                .add_property(UIProperty::ValueIsReadOnly)
                .map_err(native_error)?;
            let cached = original.build_updated_cache(&cache).map_err(native_error)?;
            result.node.secure = cached.is_cached_password().map_err(native_error)?;
            if let Ok(value) = cached.get_cached_pattern::<UIValuePattern>() {
                if !result.node.secure {
                    result.node.value = value.get_cached_value().ok();
                    if value.cached_is_readonly().is_ok_and(|readonly| !readonly) {
                        result.node.states.push("editable".into());
                    }
                }
            }
        }
        self.timeout(deadline)?;
        let mut child = match optional(
            self.walker
                .get_first_child_build_cache(&element, &self.cache),
        ) {
            Ok(child) => child,
            Err(_) => {
                result.reasons.push(Reason::ChildReadError);
                return Ok(result);
            }
        };
        if !children {
            if child.is_some() {
                result.reasons.push(Reason::DepthLimit);
            }
            return Ok(result);
        }
        let pid = handle.bus.parse().map_err(|_| Error::StaleRef)?;
        while let Some(element) = child {
            self.timeout(deadline)?;
            if result.children.len() >= 2000 {
                result.reasons.push(Reason::LargeContainerSkipped);
                break;
            }
            result
                .children
                .push(self.objects.insert(pid, element.clone()));
            child = match optional(
                self.walker
                    .get_next_sibling_build_cache(&element, &self.cache),
            ) {
                Ok(child) => child,
                Err(_) => {
                    result.reasons.push(Reason::ChildReadError);
                    break;
                }
            };
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
        let element = self.resolve(&handle, Instant::now() + Duration::from_secs(2))?;
        if action == "set_value" && element.is_password().map_err(native_error)? {
            return Err(Error::PermissionDenied);
        }
        macro_rules! perform {($pattern:ty,$method:ident $(,$value:expr)?)=>{{let pattern=element.get_pattern::<$pattern>().map_err(native_error)?;check().map_err(Error::guard)?;pattern.$method($($value)?).map_err(native_error)}};}
        match action.as_str() {
            "focus" => {
                check().map_err(Error::guard)?;
                element.set_focus().map_err(native_error)
            }
            "press" => {
                if let Ok(pattern) = element.get_pattern::<UIInvokePattern>() {
                    check().map_err(Error::guard)?;
                    pattern.invoke().map_err(native_error)
                } else {
                    perform!(UITogglePattern, toggle)
                }
            }
            "toggle" => perform!(UITogglePattern, toggle),
            "set_value" => perform!(
                UIValuePattern,
                set_value,
                &value.ok_or(Error::PermissionDenied)?
            ),
            "select" => perform!(UISelectionItemPattern, select),
            "expand" => perform!(UIExpandCollapsePattern, expand),
            "collapse" => perform!(UIExpandCollapsePattern, collapse),
            "scroll_into_view" => perform!(UIScrollItemPattern, scroll_into_view),
            _ => Err(Error::PermissionDenied),
        }
    }
}
impl AccessibilitySensor for Sensor {
    fn apps(&self) -> Task<'_, Vec<App>> {
        Box::pin(self.worker.call(Context::new, |_| {
            let mut seen = std::collections::HashSet::new();
            Ok(crate::discovery::windows()
                .map_err(|_| Error::PermissionDenied)?
                .into_iter()
                .filter(|w| seen.insert(w.pid))
                .map(|w| App {
                    app_id: w.app_id.clone(),
                    executable: w.app_id,
                    name: w.name,
                    pid: w.pid,
                    focused: w.focused,
                    handle: Handle {
                        bus: w.pid.to_string(),
                        path: "app".into(),
                    },
                })
                .collect())
        }))
    }
    fn snapshot<'a>(&'a self, root: &'a Handle, depth: usize, deadline: Instant) -> Task<'a, Tree> {
        let root = root.clone();
        Box::pin(self.worker.call(Context::new, move |c| {
            walk(root, depth, deadline, |h, children, deadline| {
                c.read(h, children, deadline)
            })
        }))
    }
    fn refresh<'a>(&'a self, handle: &'a Handle) -> Task<'a, Node> {
        let handle = handle.clone();
        Box::pin(self.worker.call(Context::new, move |c| {
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
