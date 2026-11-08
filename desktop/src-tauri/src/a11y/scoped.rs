use super::*;

pub const NODE_BUDGET: usize = 64;

#[derive(Clone, Copy)]
pub struct Position {
    pub row: i32,
    pub column: i32,
    pub rows: i32,
    pub columns: i32,
}

impl Position {
    fn valid(self) -> bool {
        self.row >= 0 && self.column >= 0 && self.row < self.rows && self.column < self.columns
    }
}

#[derive(Clone)]
pub struct Binding {
    pub aliases: Vec<String>,
    pub app: Handle,
    pub ancestors: Vec<(Node, Handle)>,
    pub target: Node,
    pub handle: Handle,
    pub position: Option<Position>,
}

#[cfg(any(target_os = "linux", test))]
pub(super) fn unique_ancestor(
    candidates: Vec<RawNode>,
    expected: &Node,
    parent: usize,
) -> Result<RawNode, Error> {
    let mut candidates: Vec<_> = candidates
        .into_iter()
        .filter(|raw| raw.node.role == expected.role && raw.node.name == expected.name)
        .collect();
    if candidates.len() > 1 {
        return Err(Error::AmbiguousTarget);
    }
    let mut node = candidates.pop().ok_or(Error::StaleRef)?;
    node.parent = Some(parent);
    Ok(node)
}

impl Service {
    pub(super) async fn prepare_bindings(&self, refs: &[String], app: &Handle) -> Vec<Binding> {
        let mut bindings = Vec::new();
        for reference in refs {
            let binding = {
                let store = self.store.lock().unwrap();
                store.snapshots.iter().find_map(|snapshot| {
                    let (target, handle) = snapshot
                        .nodes
                        .iter()
                        .find(|(n, _)| &n.reference == reference)?;
                    let mut ancestors = Vec::new();
                    let mut parent = target.parent_ref.as_deref();
                    while let Some(reference) = parent {
                        if ancestors.len() == 16 {
                            return None;
                        }
                        let (node, handle) = snapshot
                            .nodes
                            .iter()
                            .find(|(n, _)| n.reference == reference)?;
                        ancestors.push((node.clone(), handle.clone()));
                        parent = node.parent_ref.as_deref();
                    }
                    ancestors.reverse();
                    (!ancestors.is_empty()).then(|| Binding {
                        aliases: vec![reference.clone()],
                        app: app.clone(),
                        ancestors,
                        target: target.clone(),
                        handle: handle.clone(),
                        position: None,
                    })
                })
            };
            if let Some(mut binding) = binding {
                let parent = &binding.ancestors.last().unwrap().1;
                if let Ok(position) = self.sensor.position(parent, &binding.handle).await {
                    binding.position = position;
                    if binding.position.is_some_and(|position| !position.valid()) {
                        continue;
                    }
                    if std::env::var_os("RIO_A11Y_TRACE").is_some() {
                        let roles: Vec<_> = binding
                            .ancestors
                            .iter()
                            .map(|(n, _)| n.role.as_str())
                            .collect();
                        eprintln!(
                            "a11y scoped prepared ancestors={roles:?} table_position={}",
                            position.is_some()
                        );
                    }
                    bindings.push(binding);
                }
            }
        }
        bindings
    }

    pub(super) async fn scoped_get(
        &self,
        r: &Request,
        app: &Handle,
        deadline: Instant,
    ) -> Result<Value, Error> {
        let reference = r.reference.as_ref().ok_or(Error::StaleRef)?;
        let (watch_id, binding) = self
            .watch
            .lock()
            .unwrap()
            .as_ref()
            .and_then(|watch| {
                if watch.app.bus != app.bus || watch.app.path != app.path {
                    return None;
                }
                watch
                    .bindings
                    .iter()
                    .find(|b| {
                        b.aliases.contains(reference)
                            && b.app.bus == app.bus
                            && b.app.path == app.path
                    })
                    .map(|b| (watch.id.clone(), b.clone()))
            })
            .ok_or(Error::StaleRef)?;
        let epoch = self.store.lock().unwrap().epoch;
        let deadline = deadline.min(Instant::now() + Duration::from_millis(75));
        let collected = tokio::time::timeout_at(
            deadline.into(),
            self.sensor.scoped(&binding, deadline, NODE_BUDGET),
        )
        .await
        .map_err(|_| Error::StaleRef)
        .and_then(|result| result);
        let tree = collected.inspect_err(|error| {
            if std::env::var_os("RIO_A11Y_TRACE").is_some() {
                eprintln!("a11y scoped fallback stage=backend code={}", error.code());
            }
        })?;
        if !tree.complete || tree.nodes.len() > NODE_BUDGET {
            return Err(Error::StaleRef);
        }
        let query = r.query.as_ref().ok_or(Error::StaleRef)?;
        let candidates: Vec<_> = tree
            .nodes
            .iter()
            .enumerate()
            .map(|(i, raw)| {
                let mut node = raw.node.clone();
                node.protect();
                node.reference = i.to_string();
                node.parent_ref = raw.parent.map(|p| p.to_string());
                node
            })
            .collect();
        let found = matches(&candidates, query);
        if found.len() > 1 {
            return Err(Error::AmbiguousTarget);
        }
        let node = found.first().ok_or(Error::StaleRef)?;
        if node.role != binding.target.role || node.name != binding.target.name {
            return Err(Error::StaleRef);
        }
        let index: usize = node.reference.parse().map_err(|_| Error::StaleRef)?;
        let handle = tree.nodes[index].handle.clone();
        let mut ancestors = Vec::new();
        let mut parent = tree.nodes[index].parent;
        while let Some(i) = parent {
            if ancestors.len() == 16 || i >= tree.nodes.len() {
                return Err(Error::StaleRef);
            }
            ancestors.push((i, tree.nodes[i].handle.clone()));
            parent = tree.nodes[i].parent;
        }
        ancestors.reverse();
        let (id, nodes) = {
            let mut store = self.store.lock().unwrap();
            if store.epoch != epoch {
                return Err(Error::StaleRef);
            }
            store.insert(app.clone(), tree)
        };
        let node = nodes[index].clone();
        let mut watch = self.watch.lock().unwrap();
        let watch = watch
            .as_mut()
            .filter(|w| w.id == watch_id)
            .ok_or(Error::StaleRef)?;
        let plan = watch
            .bindings
            .iter_mut()
            .find(|b| b.aliases.contains(reference))
            .ok_or(Error::StaleRef)?;
        for watched in &mut watch.refs {
            if *watched == plan.target.reference {
                *watched = node.reference.clone();
            }
        }
        plan.aliases.push(node.reference.clone());
        if plan.aliases.len() > 16 {
            plan.aliases.remove(0);
        }
        plan.target = node.clone();
        plan.handle = handle;
        plan.ancestors = ancestors
            .into_iter()
            .map(|(i, h)| (nodes[i].clone(), h))
            .collect();
        if std::env::var_os("RIO_A11Y_TRACE").is_some() {
            eprintln!(
                "a11y scoped resolved nodes={} candidates={}",
                nodes.len(),
                found.len()
            );
        }
        Ok(json!({"request_id":r.request_id,"snapshot_id":id,"complete":true,"nodes":[node]}))
    }
}
