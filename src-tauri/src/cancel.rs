//! Stop and deadline for in-flight tutorial work.
//!
//! Every Stop moves the session generation forward. A step runs against the
//! generation it started with: it is dropped as soon as the generation moves
//! (without waiting for Holo), and its result is only applied while the
//! generation is unchanged.

use std::future::Future;
use std::time::Duration;
use tokio::sync::watch;

/// Total budget for one learner step: inference, retries and searches
/// together (est., not measured; each stream also has its own 20 s
/// inactivity timeout).
pub const STEP_DEADLINE: Duration = Duration::from_secs(150);

pub const STOPPED: &str = "Tutorial stopped";

pub struct Generation(watch::Sender<u64>);

impl Default for Generation {
    fn default() -> Self {
        Self(watch::Sender::new(0))
    }
}

impl Generation {
    pub fn current(&self) -> u64 {
        *self.0.borrow()
    }

    pub fn is_current(&self, generation: u64) -> bool {
        self.current() == generation
    }

    /// Invalidates everything started before now.
    pub fn bump(&self) {
        self.0.send_modify(|g| *g += 1);
    }

    /// Runs `work` until it ends, the generation moves on (Stop), or
    /// `deadline` passes, whichever comes first.
    pub async fn run<T>(
        &self,
        generation: u64,
        deadline: Duration,
        work: impl Future<Output = Result<T, String>>,
    ) -> Result<T, String> {
        let mut rx = self.0.subscribe();
        tokio::select! {
            // Stop first: work stopped before it started never runs.
            biased;
            _ = rx.wait_for(|g| *g != generation) => Err(STOPPED.into()),
            r = tokio::time::timeout(deadline, work) => r.unwrap_or_else(|_| {
                Err(format!("Holo did not answer within {} s: try again.", deadline.as_secs()))
            }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::time::Instant;

    #[test]
    fn stop_interrupts_a_slow_step() {
        let generation = Arc::new(Generation::default());
        let g = generation.current();
        let stopper = generation.clone();
        tauri::async_runtime::block_on(async move {
            tokio::spawn(async move {
                tokio::time::sleep(Duration::from_millis(50)).await;
                stopper.bump();
            });
            let started = Instant::now();
            let r: Result<(), String> = generation
                .run(g, Duration::from_secs(30), async {
                    tokio::time::sleep(Duration::from_secs(30)).await;
                    Ok(())
                })
                .await;
            assert_eq!(r.unwrap_err(), STOPPED);
            assert!(started.elapsed() < Duration::from_secs(2));
            assert!(!generation.is_current(g));
        });
    }

    #[test]
    fn stopped_before_start_never_runs() {
        let generation = Generation::default();
        let g = generation.current();
        generation.bump();
        let r = tauri::async_runtime::block_on(generation.run(g, Duration::from_secs(5), async { Ok(1) }));
        assert_eq!(r.unwrap_err(), STOPPED);
    }

    #[test]
    fn deadline_bounds_the_whole_step() {
        let generation = Generation::default();
        let r: Result<(), String> =
            tauri::async_runtime::block_on(generation.run(generation.current(), Duration::from_millis(50), async {
                tokio::time::sleep(Duration::from_secs(30)).await;
                Ok(())
            }));
        assert!(r.unwrap_err().contains("try again"));
    }
}
