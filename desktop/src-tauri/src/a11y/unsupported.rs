use super::*;
#[derive(Default)]
pub struct Sensor;
impl AccessibilitySensor for Sensor {
    fn apps(&self) -> Task<'_, Vec<App>> {
        Box::pin(async { Err(Error::PermissionDenied) })
    }
    fn snapshot<'a>(&'a self, _: &'a Handle, _: usize, _: Instant) -> Task<'a, Tree> {
        Box::pin(async { Err(Error::PermissionDenied) })
    }
    fn refresh<'a>(&'a self, _: &'a Handle) -> Task<'a, Node> {
        Box::pin(async { Err(Error::PermissionDenied) })
    }
    fn action<'a>(
        &'a self,
        _: &'a Handle,
        _: &'a str,
        _: Option<&'a str>,
        _: &'a input::ActionGuard<'a>,
    ) -> Task<'a, ()> {
        Box::pin(async { Err(Error::PermissionDenied) })
    }
}
