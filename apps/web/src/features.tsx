import { FormEvent, useEffect, useState, type CSSProperties } from "react";
import { money, percent } from "./lib/format";

type Config = { id: string; name: string; model: string };
type Workflow = {
  id: string;
  name: string;
  project_id?: string;
  project_name?: string;
  task_type?: string;
};
type Props = {
  page: string;
  workflowId: string;
  workflows: Workflow[];
  refresh: () => void;
};
const box: CSSProperties = {
  background: "#fff",
  border: "1px solid #e8ece8",
  borderRadius: 8,
  padding: 18,
  marginTop: 14,
};

export function FeaturePage({ page, workflowId, workflows, refresh }: Props) {
  const workflow = workflowId || workflows[0]?.id || "";
  if (page === "Workflows")
    return <Workflows workflows={workflows} refresh={refresh} />;
  if (page === "Executions") return <Executions workflowId={workflow} />;
  if (page === "Compare") return <Compare workflowId={workflow} />;
  if (page === "Scenarios") return <Scenarios workflowId={workflow} />;
  if (page === "Imports") return <Imports />;
  return <Settings workflowId={workflow} />;
}

function Workflows({
  workflows,
  refresh,
}: {
  workflows: Workflow[];
  refresh: () => void;
}) {
  const [projects, setProjects] = useState<any[]>([]),
    [message, setMessage] = useState("");
  useEffect(() => {
    fetch("/api/projects")
      .then((r) => r.json())
      .then(setProjects);
  }, []);
  async function createProject(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: f.get("name"),
        description: f.get("description"),
      }),
    });
    setMessage(r.ok ? "Project created." : await r.text());
    if (r.ok) {
      e.currentTarget.reset();
      setProjects(await fetch("/api/projects").then((x) => x.json()));
    }
  }
  async function createWorkflow(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await fetch("/api/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: f.get("project_id"),
        name: f.get("name"),
        task_type: f.get("task_type"),
        baseline_hourly_rate: f.get("hourly_rate"),
        baseline_minutes: f.get("baseline_minutes"),
      }),
    });
    setMessage(r.ok ? "Workflow created." : await r.text());
    if (r.ok) {
      e.currentTarget.reset();
      refresh();
    }
  }
  return (
    <div className="featurePage">
      <h2>Projects and workflows</h2>
      <p>
        Create the business process and its human-only baseline assumptions.
      </p>
      <div className="featureGrid">
        <form style={box} onSubmit={createProject}>
          <h3>New project</h3>
          <label>
            Name
            <input name="name" required maxLength={160} />
          </label>
          <label>
            Description
            <input name="description" maxLength={2000} />
          </label>
          <button className="primary">Create project</button>
        </form>
        <form style={box} onSubmit={createWorkflow}>
          <h3>New workflow</h3>
          <label>
            Project
            <select name="project_id" required>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Name
            <input name="name" required />
          </label>
          <label>
            Task type
            <input name="task_type" defaultValue="general" />
          </label>
          <div className="formRow">
            <label>
              Human hourly rate (USD)
              <input
                name="hourly_rate"
                type="number"
                min="0"
                step="0.01"
                defaultValue="24"
              />
            </label>
            <label>
              Baseline minutes
              <input
                name="baseline_minutes"
                type="number"
                min="0"
                step="0.1"
                defaultValue="12"
              />
            </label>
          </div>
          <button className="primary">Create workflow</button>
        </form>
      </div>
      <div style={box}>
        <h3>Configured workflows and configurations</h3>
        {workflows.map((w) => (
          <div key={w.id} className="workflowManager">
            <div className="featureListRow">
              <b>{w.name}</b>
              <span>
                {w.project_name} · {w.task_type}
              </span>
            </div>
            <ConfigManager workflow={w} />
          </div>
        ))}
      </div>
      {message && <p className="notice">{message}</p>}
    </div>
  );
}

function ConfigManager({ workflow }: { workflow: Workflow }) {
  const [items, setItems] = useState<Config[]>([]),
    [message, setMessage] = useState("");
  async function load() {
    setItems(
      await fetch(`/api/workflows/${workflow.id}/configurations`).then((r) =>
        r.json(),
      ),
    );
  }
  useEffect(() => {
    load();
  }, [workflow.id]);
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await fetch(`/api/workflows/${workflow.id}/configurations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: f.get("name"), model: f.get("model") }),
    });
    setMessage(r.ok ? "Configuration added." : await r.text());
    if (r.ok) {
      e.currentTarget.reset();
      load();
    }
  }
  return (
    <div className="configManager">
      {items.map((x) => (
        <span key={x.id} className="miniChip">
          {x.name} · {x.model}
        </span>
      ))}
      <form className="featureToolbar" onSubmit={create}>
        <input name="name" placeholder="Configuration name" required />
        <input name="model" placeholder="Model identifier" required />
        <button className="primary">Add configuration</button>
      </form>
      {message && <small>{message}</small>}
    </div>
  );
}

function Executions({ workflowId }: { workflowId: string }) {
  const [items, setItems] = useState<any[]>([]),
    [total, setTotal] = useState(0),
    [search, setSearch] = useState(""),
    [selected, setSelected] = useState<any>(null),
    [detail, setDetail] = useState<any>(null),
    [message, setMessage] = useState("");
  async function load() {
    const q = new URLSearchParams({ limit: "100" });
    if (workflowId) q.set("workflow_id", workflowId);
    if (search) q.set("search", search);
    const x = await fetch("/api/executions?" + q);
    const d = await x.json();
    setItems(d.items);
    setTotal(d.total);
  }
  useEffect(() => {
    load();
  }, [workflowId, search]);
  async function open(row: any) {
    setSelected(row);
    setDetail(
      await fetch(`/api/executions/${encodeURIComponent(row.id)}`).then((r) =>
        r.json(),
      ),
    );
  }
  async function verify(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await fetch(
      `/api/verifications/${encodeURIComponent(selected.id)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: f.get("status"),
          verified_by: f.get("verified_by"),
          reference: f.get("reference"),
          reasoning: f.get("reasoning"),
        }),
      },
    );
    setMessage(r.ok ? "Verification saved." : await r.text());
    if (r.ok) {
      await load();
      await open(selected);
    }
  }
  return (
    <div className="featurePage">
      <h2>Execution explorer</h2>
      <p>
        {total} executions. Select a run to inspect its operation costs, retry
        history, and verification evidence.
      </p>
      <div className="featureToolbar">
        <input
          placeholder="Search task case, ID, or category"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <a href={`/api/reports/workflow.csv?workflow_id=${workflowId}`}>
          Export CSV
        </a>
      </div>
      <div className="tableScroll" style={box}>
        <table className="wideTable">
          <thead>
            <tr>
              <th>Task case</th>
              <th>Configuration</th>
              <th>Runtime</th>
              <th>Outcome</th>
              <th>Attempts</th>
              <th>Inference</th>
              <th>Tools</th>
              <th>Human</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {items.map((x) => (
              <tr
                tabIndex={0}
                role="button"
                aria-label={`Inspect ${x.task_case_id}, ${x.outcome}`}
                key={x.id}
                onClick={() => open(x)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    open(x);
                  }
                }}
              >
                <td>{x.task_case_id}</td>
                <td>{x.configuration}</td>
                <td>{x.runtime_status}</td>
                <td>{x.outcome}</td>
                <td>{x.attempts}</td>
                <td>{money(String(x.inference_cost))}</td>
                <td>{money(String(x.tool_cost))}</td>
                <td>
                  {money(
                    String(Number(x.human_cost) + Number(x.fallback_cost)),
                  )}
                </td>
                <td>{money(String(x.total_cost))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected && detail && (
        <div style={box}>
          <div className="featureToolbar">
            <div>
              <h3>{selected.task_case_id} · execution details</h3>
              <span>{selected.id}</span>
            </div>
            <button
              onClick={() => {
                setSelected(null);
                setDetail(null);
              }}
            >
              Close
            </button>
          </div>
          <div className="featureGrid">
            <div>
              <h4>Cost breakdown</h4>
              <p>Inference: {money(String(selected.inference_cost))}</p>
              <p>Tools: {money(String(selected.tool_cost))}</p>
              <p>Review/correction: {money(String(selected.human_cost))}</p>
              <p>Fallback: {money(String(selected.fallback_cost))}</p>
              <b>Total attributed: {money(String(selected.total_cost))}</b>
              <h4>Logical attempts</h4>
              {detail.attempts.map((a: any) => (
                <p key={a.id}>
                  Attempt {a.attempt_number}: {a.status} {a.retry_reason || ""}
                </p>
              ))}
              <h4>Model calls</h4>
              {detail.model_calls.map((x: any) => (
                <p key={x.id}>
                  {x.provider || "Unknown provider"} /{" "}
                  {x.model || "Unknown model"} · {x.input_tokens} input,{" "}
                  {x.output_tokens} output ·{" "}
                  {money(x.reported_cost ?? x.calculated_cost)}
                </p>
              ))}
              <h4>Tool calls</h4>
              {detail.tool_calls.map((x: any) => (
                <p key={x.id}>
                  {x.name} · {x.status} · {money(x.cost)}
                </p>
              ))}
              <h4>Human work</h4>
              {detail.human_work.map((x: any) => (
                <p key={x.id}>
                  {x.category} · {x.minutes} min at ${x.hourly_rate}/hr ·{" "}
                  {money(x.cost)}
                </p>
              ))}
            </div>
            <div>
              <h4>Outcome evidence</h4>
              {detail.evidence.map((v: any) => (
                <p key={v.id}>
                  {v.status} · {v.method} · {v.reference || "No reference"}
                </p>
              ))}
              <form onSubmit={verify}>
                <h4>Record manual verification</h4>
                <label>
                  Outcome
                  <select name="status">
                    <option value="verified_success">Verified success</option>
                    <option value="verified_failure">Verified failure</option>
                    <option value="indeterminate">Indeterminate</option>
                  </select>
                </label>
                <label>
                  Reviewer label
                  <input name="verified_by" required maxLength={160} />
                </label>
                <label>
                  Evidence reference
                  <input name="reference" maxLength={1000} />
                </label>
                <label>
                  Reasoning
                  <input name="reasoning" maxLength={4000} />
                </label>
                <button className="primary">Save verification</button>
              </form>
            </div>
          </div>
          {message && <p className="notice">{message}</p>}
        </div>
      )}
    </div>
  );
}

function Compare({ workflowId }: { workflowId: string }) {
  const [configs, setConfigs] = useState<Config[]>([]),
    [a, setA] = useState(""),
    [b, setB] = useState(""),
    [result, setResult] = useState<any>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (workflowId)
      fetch(`/api/workflows/${workflowId}/configurations`)
        .then((r) => r.json())
        .then((v: Config[]) => {
          setConfigs(v);
          setA(v[0]?.id || "");
          setB(v[1]?.id || "");
        });
  }, [workflowId]);
  async function run() {
    const r = await fetch(
      `/api/compare?workflow_id=${workflowId}&a=${a}&b=${b}`,
    );
    if (!r.ok) {
      setError(await r.text());
      return;
    }
    setError("");
    setResult(await r.json());
  }
  const cards = result ? (Object.values(result.configurations) as any[]) : [];
  return (
    <div className="featurePage">
      <h2>Paired configuration comparison</h2>
      <p>
        Only stable task-case IDs present in both configurations enter the
        paired cohort. Descriptive results do not imply statistical
        significance.
      </p>
      <div className="featureToolbar">
        <label>
          Configuration A
          <select value={a} onChange={(e) => setA(e.target.value)}>
            {configs.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Configuration B
          <select value={b} onChange={(e) => setB(e.target.value)}>
            {configs.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="primary"
          onClick={run}
          disabled={!a || !b || a === b}
        >
          Compare matched tasks
        </button>
      </div>
      {error && <p className="notice">{error}</p>}
      {result && (
        <>
          <div className="featureGrid">
            {cards.map((c: any) => (
              <div style={box} key={c.name}>
                <h3>{c.name}</h3>
                <p>{c.cases} matched task cases</p>
                <div className="score">
                  {money(c.metrics.cost_per_verified_success)}
                </div>
                <p>Cost per verified success</p>
                <div className="featureListRow">
                  <span>Evaluated success rate</span>
                  <b>{percent(c.metrics.evaluated_success_rate)}</b>
                </div>
                <div className="featureListRow">
                  <span>Total attributed cost</span>
                  <b>{money(c.metrics.total_cost)}</b>
                </div>
                <div className="featureListRow">
                  <span>Retry attempts</span>
                  <b>{c.metrics.retry_attempts ?? "Not attributed"}</b>
                </div>
                <div className="featureListRow">
                  <span>Resolved-cohort savings</span>
                  <b>{money(c.metrics.net_savings_resolved)}</b>
                </div>
                {c.metrics.warnings?.map((w: string) => (
                  <p className="warning" key={w}>
                    {w}
                  </p>
                ))}
              </div>
            ))}
          </div>
          <p className="notice">
            {result.matched_cases} matched cases · {result.unmatched_cases[a]}{" "}
            unmatched in A · {result.unmatched_cases[b]} unmatched in B
          </p>
          <div style={box}>
            <h3>Task-level results</h3>
            <div className="tableScroll">
              <table className="wideTable">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>A outcome</th>
                    <th>A cost</th>
                    <th>B outcome</th>
                    <th>B cost</th>
                  </tr>
                </thead>
                <tbody>
                  {result.case_rows.map((r: any) => (
                    <tr key={r.task_case_id}>
                      <td>{r.task_case_id}</td>
                      <td>{r.a.outcome}</td>
                      <td>{money(String(r.a.total_cost))}</td>
                      <td>{r.b.outcome}</td>
                      <td>{money(String(r.b.total_cost))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Scenarios({ workflowId }: { workflowId: string }) {
  const [assumptions, setAssumptions] = useState({
      hourly_rate: "30",
      baseline_minutes: "8",
      review_minutes: "0.6",
      correction_minutes: "0",
      model_cost_multiplier: "1",
      monthly_fixed_cost_usd: "0",
      monthly_volume: "1000",
    }),
    [result, setResult] = useState<any>(null),
    [error, setError] = useState("");
  async function evaluate(e: FormEvent) {
    e.preventDefault();
    const r = await fetch("/api/scenario", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow_id: workflowId, ...assumptions }),
    });
    const x = await r.json();
    if (!r.ok) {
      setError(JSON.stringify(x));
      return;
    }
    setError("");
    setResult(x);
  }
  return (
    <div className="featurePage">
      <h2>Scenario playground</h2>
      <p>
        Revalue the selected workflow under explicit assumptions. Stored
        observations are not changed.
      </p>
      <form style={box} onSubmit={evaluate}>
        <div className="featureGrid">
          {[
            ["hourly_rate", "Human hourly rate (USD)"],
            ["baseline_minutes", "Human baseline minutes"],
            ["review_minutes", "Review minutes per execution"],
            ["correction_minutes", "Correction minutes per execution"],
            ["model_cost_multiplier", "Model/tool cost multiplier"],
            ["monthly_fixed_cost_usd", "Monthly fixed overhead (USD)"],
            ["monthly_volume", "Monthly execution volume"],
          ].map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                min="0"
                step="0.1"
                value={(assumptions as any)[key]}
                onChange={(e) =>
                  setAssumptions({ ...assumptions, [key]: e.target.value })
                }
              />
            </label>
          ))}
        </div>
        <button className="primary">Recalculate scenario</button>
      </form>
      {error && <p className="warning">{error}</p>}
      {result && (
        <div style={box}>
          <span className="tag">SCENARIO · NOT HISTORICAL</span>
          <div className="featureGrid scenarioMetrics">
            <div>
              <small>Cost per verified success</small>
              <b>{money(result.metrics.cost_per_verified_success)}</b>
            </div>
            <div>
              <small>Net savings · resolved cases</small>
              <b>{money(result.metrics.net_savings_resolved)}</b>
            </div>
            <div>
              <small>Cost per execution</small>
              <b>{money(result.metrics.cost_per_execution)}</b>
            </div>
            <div>
              <small>Break-even hourly rate</small>
              <b>{money(result.break_even_hourly_rate)}</b>
            </div>
          </div>
          <h3>Savings sensitivity to labor rate</h3>
          <div className="tableScroll">
            <table className="wideTable">
              <thead>
                <tr>
                  <th>Hourly rate</th>
                  <th>Net savings · resolved cohort</th>
                </tr>
              </thead>
              <tbody>
                {result.sensitivity.map((x: any) => (
                  <tr key={x.hourly_rate}>
                    <td>${x.hourly_rate}/hr</td>
                    <td>{money(x.net_savings)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Assumptions used</summary>
            <pre>{JSON.stringify(result.assumptions, null, 2)}</pre>
          </details>
          <p className="notice">
            Observed outcomes and task mix are held fixed. Review/correction
            durations and model/tool cost multiplier are scenario assumptions;
            missing usage costs remain incomplete. Fixed monthly overhead is
            allocated across the stated volume.
          </p>
        </div>
      )}
    </div>
  );
}

function Imports() {
  const [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState<any>(null),
    [result, setResult] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function send(dry: boolean) {
    if (!file) return;
    setBusy(true);
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/imports" + (dry ? "?dry_run=true" : ""), {
      method: "POST",
      body: fd,
    });
    const body = await r.json();
    if (!r.ok)
      setError(
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail),
      );
    else setResult(body);
    setBusy(false);
  }
  async function choose(f: File | null) {
    setFile(f);
    setResult(null);
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/api/imports/preview", { method: "POST", body: fd });
    const v = await r.json();
    if (!r.ok) {
      setError(JSON.stringify(v.detail));
      return;
    }
    setError("");
    setPreview(v);
  }
  return (
    <div className="featurePage">
      <h2>Import data</h2>
      <p>
        Files stay local. Preview and validate before committing a transaction.
      </p>
      <div style={box}>
        <label className="uploadBox">
          Choose JSON, JSONL, or execution CSV
          <input
            type="file"
            accept=".json,.jsonl,.csv,application/json,text/csv"
            onChange={(e) => choose(e.target.files?.[0] || null)}
          />
        </label>
        <a href="/examples/support-triage/executions-template.csv" download>
          Download execution CSV template
        </a>
        {preview && (
          <>
            <h3>Preview · {file?.name}</h3>
            <p>
              {preview.rows} rows · {preview.format} · checksum{" "}
              {preview.checksum}
            </p>
            {preview.note && <p className="notice">{preview.note}</p>}
            <pre>{JSON.stringify(preview.sample, null, 2)}</pre>
            <div className="featureToolbar">
              <button disabled={busy} onClick={() => send(true)}>
                Validate dry run
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() => send(false)}
              >
                Import transaction
              </button>
            </div>
          </>
        )}
        {result && (
          <p className="notice">
            {result.duplicate
              ? "This exact file was already imported."
              : result.dry_run
                ? `Dry run valid: ${result.accepted} records would be accepted.`
                : `Imported ${result.accepted} records.`}
          </p>
        )}
        {error && <p className="warning">{error}</p>}
      </div>
      <div style={box}>
        <h3>Import history</h3>
        <ImportHistory />
      </div>
      <div style={box}>
        <h3>OTLP/JSON span import</h3>
        <p>
          Use the explicit mapping API at <code>/api/imports/otel/preview</code>{" "}
          to map trace IDs to task-case IDs. Imported telemetry always leaves
          business outcome unverified.
        </p>
      </div>
    </div>
  );
}
function ImportHistory() {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    fetch("/api/imports")
      .then((r) => r.json())
      .then((d) => setItems(d.items));
  }, []);
  return (
    <div>
      {items.map((x) => (
        <div className="featureListRow" key={x.id}>
          <span>{x.filename}</span>
          <b>
            {x.rows_accepted} events · {x.status}
          </b>
          <small>{x.imported_at}</small>
        </div>
      ))}
    </div>
  );
}

function Settings({ workflowId }: { workflowId: string }) {
  const [message, setMessage] = useState("");
  async function saveBaseline(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await fetch("/api/baselines", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workflow_id: workflowId,
        name: f.get("name"),
        hourly_rate: f.get("hourly_rate"),
        typical_minutes: f.get("minutes"),
        source: "user_provided",
        confidence: "assumption",
      }),
    });
    setMessage(r.ok ? "Baseline saved as a new version." : await r.text());
  }
  async function savePrice(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await fetch("/api/pricing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: f.get("provider"),
        model: f.get("model"),
        effective_from: f.get("effective_from"),
        currency: "USD",
        input_price_per_million: f.get("input"),
        output_price_per_million: f.get("output"),
        source_type: "user_provided",
      }),
    });
    setMessage(r.ok ? "Pricing version saved." : await r.text());
  }
  return (
    <div className="featurePage">
      <h2>Baselines and model pricing</h2>
      <p>
        Version assumptions explicitly. Pricing is matched by provider, model,
        and effective date.
      </p>
      <div className="featureGrid">
        <form style={box} onSubmit={saveBaseline}>
          <h3>Human baseline profile</h3>
          <label>
            Profile name
            <input name="name" required defaultValue="Human-only task" />
          </label>
          <label>
            Hourly rate (USD)
            <input
              name="hourly_rate"
              type="number"
              min="0"
              step="0.01"
              required
            />
          </label>
          <label>
            Typical minutes
            <input name="minutes" type="number" min="0" step="0.1" required />
          </label>
          <button className="primary">Save baseline version</button>
        </form>
        <form style={box} onSubmit={savePrice}>
          <h3>Model pricing profile</h3>
          <label>
            Provider
            <input name="provider" required />
          </label>
          <label>
            Model identifier
            <input name="model" required />
          </label>
          <label>
            Effective from
            <input name="effective_from" type="datetime-local" required />
          </label>
          <div className="formRow">
            <label>
              Input / 1M tokens USD
              <input
                name="input"
                type="number"
                min="0"
                step="0.000001"
                required
              />
            </label>
            <label>
              Output / 1M tokens USD
              <input
                name="output"
                type="number"
                min="0"
                step="0.000001"
                required
              />
            </label>
          </div>
          <button className="primary">Save pricing version</button>
        </form>
      </div>
      {message && <p className="notice">{message}</p>}
      <p className="notice">
        Existing report totals are not rewritten; imported calls retain the
        pricing source used when calculated.
      </p>
    </div>
  );
}
