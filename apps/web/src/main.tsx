import {
  Activity,
  ArrowDownRight,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Download,
  FileUp,
  LayoutDashboard,
  Search,
  Settings2,
  ShieldAlert,
  Workflow,
} from "lucide-react";
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { FeaturePage } from "./features";
import { money, percent as pct } from "./lib/format";
import "./style.css";
type Metrics = {
  executions: number;
  verified_successes: number;
  verified_failures: number;
  unknown_outcomes: number;
  verified_success_fraction: string | null;
  evaluated_success_rate: string | null;
  total_cost: string;
  cost_per_execution: string | null;
  cost_per_verified_success: string | null;
  cost_per_resolved_task: string | null;
  net_savings_resolved: string;
  excluded_unresolved: number;
  provisional: boolean;
};
type Dash = {
  metrics: Metrics;
  cost_composition: Record<string, string>;
  outcomes: Record<string, number>;
  configurations: { id: string; name: string; metrics: Metrics }[];
  categories: { category: string; executions: number; total_cost: string }[];
  workflows: { id: string; name: string; project_name: string }[];
  data_quality: {
    unverified: number;
    missing_baselines: number;
    currency: string;
    warnings: string[];
    model_pricing_coverage: string;
    verified_outcome_coverage: string;
    baseline_coverage: string;
    human_work_record_coverage: string;
    conflicting_evidence: number;
    unpriced_operations: number;
  };
};
type Ex = {
  id: string;
  configuration: string;
  task_case_id: string;
  category: string;
  runtime_status: string;
  outcome: string;
  attempts: number;
  inference_cost: string;
  tool_cost: string;
  human_cost: string;
  fallback_cost: string;
  total_cost: string;
  started_at: string;
};

function App() {
  const [data, setData] = useState<Dash | null>(null),
    [execs, setExecs] = useState<Ex[]>([]),
    [workflow, setWorkflow] = useState(""),
    [tab, setTab] = useState("Overview"),
    [search, setSearch] = useState(""),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0);
  async function load() {
    try {
      const suffix = workflow ? `?workflow_id=${workflow}` : "";
      const [d, e] = await Promise.all([
        fetch("/api/dashboard" + suffix),
        fetch("/api/executions" + (workflow ? `?workflow_id=${workflow}` : "")),
      ]);
      if (!d.ok || !e.ok) throw new Error("API unavailable");
      setData(await d.json());
      setExecs((await e.json()).items);
      setError("");
    } catch {
      setError(
        "Cannot reach the local API. Start the backend and load the demo dataset to explore AI Workflow Cost Analyzer.",
      );
    }
  }
  useEffect(() => {
    load();
  }, [workflow, revision]);
  const m = data?.metrics;
  const filtered = execs.filter((x) =>
    `${x.id} ${x.task_case_id} ${x.configuration} ${x.category}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <span className="mark">
            <Activity size={19} />
          </span>
          <span>AI Workflow Cost Analyzer</span>
        </div>
        <div className="workspace">
          <small>WORKSPACE</small>
          <span className="select">Local workspace</span>
        </div>
        <nav>
          {[
            ["Overview", LayoutDashboard],
            ["Workflows", Workflow],
            ["Executions", Activity],
            ["Compare", BarChart3],
            ["Scenarios", Settings2],
            ["Imports", FileUp],
          ].map(([name, Icon]: any) => (
            <button
              className={tab === name ? "active" : ""}
              onClick={() => setTab(name)}
              key={name}
            >
              <Icon size={17} />
              {name}
              {name === "Imports" && <span className="navDot" />}
            </button>
          ))}
        </nav>
        <div className="asideBottom">
          <div className="local">
            <span className="live" />
            Local data only <CircleHelp size={14} />
          </div>
          <button onClick={() => setTab("Settings")}>
            <Settings2 size={17} />
            Settings
          </button>
          <div className="profile">
            <div className="avatar">OM</div>
            <div>
              <b>Local workspace</b>
              <small>Personal analysis</small>
            </div>
            <ChevronDown size={14} />
          </div>
        </div>
      </aside>
      <main>
        <header>
          <div className="crumb">
            Workspace <span>/</span> <b>{tab}</b>
          </div>
          <div className="headActions">
            <select
              aria-label="Workflow"
              value={workflow}
              onChange={(e) => setWorkflow(e.target.value)}
            >
              <option value="">All workflows</option>
              {data?.workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
            <a
              className="iconButton"
              href={`/api/reports/workflow.json${workflow ? `?workflow_id=${encodeURIComponent(workflow)}` : ""}`}
              title="Download report"
            >
              <Download size={17} />
            </a>
            <div className="avatar smallAvatar">RJ</div>
          </div>
        </header>
        <section className="content">
          <div className="titleRow">
            <div>
              <div className="eyebrow">
                {new Date()
                  .toLocaleDateString(undefined, {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })
                  .toUpperCase()}{" "}
                <span className="badge">DEMO DATA</span>
              </div>
              <h1>{tab === "Overview" ? "Workflow economics" : tab}</h1>
              <p className="sub">
                Measure the cost of a verified business result, including every
                retry and human touch.
              </p>
            </div>
            <button
              className="outline"
              onClick={() => document.getElementById("upload")?.click()}
            >
              <FileUp size={16} /> Import data
              <input
                id="upload"
                type="file"
                hidden
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    const f = new FormData();
                    f.append("file", file);
                    const r = await fetch("/api/imports/preview", {
                      method: "POST",
                      body: f,
                    });
                    alert(
                      r.ok
                        ? JSON.stringify(await r.json(), null, 2)
                        : await r.text(),
                    );
                  }
                }}
              />
            </button>
          </div>
          {error && (
            <div className="error">
              <ShieldAlert />
              {error}
              <span>API: localhost:8000 · Web: localhost:5173</span>
            </div>
          )}
          {tab !== "Overview" ? (
            <FeaturePage
              page={tab}
              workflowId={workflow}
              workflows={data?.workflows ?? []}
              refresh={() => setRevision((v) => v + 1)}
            />
          ) : (
            <>
              {data && (
                <>
                  <div className="scope">
                    <span>
                      <span className="live" /> Live analysis
                    </span>
                    <span>·</span>
                    <span>{m?.executions ?? 0} executions</span>
                    <span>·</span>
                    <span>{data.data_quality.currency} only</span>
                    <span className="scopeRight">Updated just now</span>
                  </div>
                  <div className="cards">
                    <article className="metricCard featured">
                      <div className="metricTop">
                        <span>Cost per verified success</span>
                        <CircleHelp size={15} />
                      </div>
                      <strong>{money(m?.cost_per_verified_success)}</strong>
                      <div className="metricFoot">
                        <span>Failed runs and retries included</span>
                        <span>
                          Across {m?.verified_successes ?? 0} verified results
                        </span>
                      </div>
                    </article>
                    <Metric
                      title="Total workflow cost"
                      value={money(m?.total_cost)}
                      foot={`${m?.executions ?? 0} total executions`}
                      icon="cost"
                    />
                    <Metric
                      title="Verified success rate"
                      value={pct(m?.evaluated_success_rate ?? null)}
                      foot={`${m?.verified_successes ?? 0} success · ${m?.verified_failures ?? 0} failed`}
                      icon="success"
                    />
                    <Metric
                      title="Net savings · resolved"
                      value={money(m?.net_savings_resolved)}
                      foot={`${m?.excluded_unresolved ?? 0} unresolved excluded`}
                      icon="savings"
                    />
                  </div>
                  <div className="grid2">
                    <section className="panel">
                      <div className="panelHead">
                        <div>
                          <h2>Configuration economics</h2>
                          <p>Cost of getting the business task right</p>
                        </div>
                        <span className="tag">CONFIG SUMMARY</span>
                      </div>
                      <div className="configRows">
                        {data.configurations.map((c, i) => (
                          <div className="configRow" key={c.id}>
                            <div className={`configIcon i${i}`}>
                              <Activity size={17} />
                            </div>
                            <div className="configName">
                              <b>{c.name}</b>
                              <small>
                                {c.metrics.executions} runs ·{" "}
                                {c.metrics.verified_successes} verified
                                successes
                              </small>
                            </div>
                            <div className="configCost">
                              <b>
                                {money(c.metrics.cost_per_verified_success)}
                              </b>
                              <small>per verified success</small>
                            </div>
                            <div className="successPill">
                              {pct(c.metrics.evaluated_success_rate)}
                            </div>
                          </div>
                        ))}
                      </div>
                      <div className="insight">
                        <span className="insightIcon">
                          <CheckCircle2 size={17} />
                        </span>
                        <div>
                          <b>Token price isn’t the whole story</b>
                          <p>
                            Configuration costs include retries and verified
                            outcomes, so token price alone does not determine
                            cost per successful task.
                          </p>
                        </div>
                      </div>
                    </section>
                    <section className="panel">
                      <div className="panelHead">
                        <div>
                          <h2>Where the cost goes</h2>
                          <p>
                            Attributed spend · retries included in inference and
                            tools
                          </p>
                        </div>
                        <button className="more">···</button>
                      </div>
                      <div className="chartWrap">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart
                            data={Object.entries(data.cost_composition)
                              .filter(([, v]) => Number(v) > 0)
                              .map(([name, value]) => ({
                                name: name
                                  .replace("_cost", "")
                                  .replace("_", " "),
                                value: Number(value),
                              }))}
                            layout="vertical"
                            margin={{ left: 12, right: 18, top: 8, bottom: 4 }}
                          >
                            <CartesianGrid
                              strokeDasharray="3 3"
                              horizontal={false}
                              stroke="#edf0ed"
                            />
                            <XAxis
                              type="number"
                              tickFormatter={(v) => `$${v}`}
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "#8b918c", fontSize: 11 }}
                            />
                            <YAxis
                              type="category"
                              dataKey="name"
                              axisLine={false}
                              tickLine={false}
                              tick={{ fill: "#555e57", fontSize: 12 }}
                              width={88}
                            />
                            <Tooltip formatter={(v: any) => money(String(v))} />
                            <Bar
                              dataKey="value"
                              fill="#48856c"
                              radius={[0, 5, 5, 0]}
                              barSize={23}
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="chartLegend">
                        <span>
                          <i className="legendGreen" />
                          Observed costs
                        </span>
                        <span className="muted">USD · all executions</span>
                      </div>
                    </section>
                  </div>
                  <div className="grid2 lower">
                    <section className="panel">
                      <div className="panelHead">
                        <div>
                          <h2>Outcome confidence</h2>
                          <p>
                            Unknown outcomes stay out of evaluated success rate
                          </p>
                        </div>
                        <span className="tag">
                          {m?.provisional ? "PROVISIONAL" : "EVALUATED"}
                        </span>
                      </div>
                      <div className="outcomeStats">
                        {[
                          [
                            "Verified success",
                            data.outcomes.verified_success,
                            "#4c8c6f",
                          ],
                          [
                            "Verified failure",
                            data.outcomes.verified_failure,
                            "#d27b64",
                          ],
                          [
                            "Unverified / unknown",
                            data.outcomes.unknown,
                            "#d1a350",
                          ],
                        ].map((x) => (
                          <div className="outcome" key={String(x[0])}>
                            <b>{x[1]}</b>
                            <span>{x[0]}</span>
                            <i
                              style={{
                                background: x[2] as string,
                                width: `${m?.executions ? 100 * (Number(x[1]) / m.executions) : 0}%`,
                              }}
                            />
                          </div>
                        ))}
                      </div>
                      <div className="qualityNote">
                        <ShieldAlert size={15} />
                        <div>
                          <b>Evidence coverage</b>
                          <p>
                            Outcomes{" "}
                            {pct(data.data_quality.verified_outcome_coverage)} ·
                            priced model calls{" "}
                            {pct(data.data_quality.model_pricing_coverage)} ·
                            baselines {pct(data.data_quality.baseline_coverage)}{" "}
                            · human work recorded{" "}
                            {pct(data.data_quality.human_work_record_coverage)}
                          </p>
                          {data.data_quality.warnings.map((w) => (
                            <p key={w}>{w}</p>
                          ))}
                          {data.data_quality.warnings.length === 0 && (
                            <p>
                              No current data-quality warnings. Runtime
                              completion is not itself business success.
                            </p>
                          )}
                        </div>
                      </div>
                    </section>
                    <section className="panel">
                      <div className="panelHead">
                        <div>
                          <h2>Cost by task category</h2>
                          <p>Actual attributed cost by task category</p>
                        </div>
                        <button
                          className="textButton"
                          onClick={() => setTab("Executions")}
                        >
                          View executions →
                        </button>
                      </div>
                      <div className="categoryList">
                        {data.categories.map((c) => (
                          <div className="category" key={c.category}>
                            <span>{c.category}</span>
                            <div className="track">
                              <i
                                style={{
                                  width: `${Math.max(2, (Number(c.total_cost) / (Math.max(...data.categories.map((x) => Number(x.total_cost)), 1) * 1)) * 100)}%`,
                                }}
                              />
                            </div>
                            <b>{money(c.total_cost)}</b>
                            <small>{c.executions} runs</small>
                          </div>
                        ))}
                      </div>
                    </section>
                  </div>
                  <section className="panel tablePanel">
                    <div className="panelHead tableHeading">
                      <div>
                        <h2>Recent executions</h2>
                        <p>
                          Every attempt contributes to the cost of this
                          execution
                        </p>
                      </div>
                      <div className="tableActions">
                        <label className="search">
                          <Search size={15} />
                          <input
                            placeholder="Search executions"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                          />
                        </label>
                        <button
                          className="textButton"
                          onClick={() => setTab("Executions")}
                        >
                          View all →
                        </button>
                      </div>
                    </div>
                    <div className="tableScroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Task case</th>
                            <th>Configuration</th>
                            <th>Outcome</th>
                            <th>Attempts</th>
                            <th>Inference</th>
                            <th>Human work</th>
                            <th>Total cost</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filtered.slice(0, 7).map((x) => (
                            <tr key={x.id}>
                              <td>
                                <b>{x.task_case_id}</b>
                                <small>{x.category}</small>
                              </td>
                              <td>{x.configuration}</td>
                              <td>
                                <span
                                  className={`status ${x.outcome === "verified_success" ? "ok" : x.outcome === "verified_failure" ? "fail" : "unknown"}`}
                                >
                                  <i />
                                  {x.outcome
                                    .replace("verified_", "")
                                    .replace("_", " ")}
                                </span>
                              </td>
                              <td>{x.attempts}</td>
                              <td>{money(x.inference_cost)}</td>
                              <td>
                                {money(
                                  (
                                    Number(x.human_cost) +
                                    Number(x.fallback_cost)
                                  ).toFixed(6),
                                )}
                              </td>
                              <td>
                                <b>{money(x.total_cost)}</b>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                  <footer>
                    <span>
                      AI Workflow Cost Analyzer <b>·</b> Local-first workflow
                      economics
                    </span>
                    <span>
                      <i className="live" /> Data stays on this machine
                    </span>
                  </footer>
                </>
              )}
            </>
          )}
        </section>
      </main>
    </div>
  );
}
function Metric({
  title,
  value,
  foot,
  icon,
}: {
  title: string;
  value: string;
  foot: string;
  icon: string;
}) {
  return (
    <article className="metricCard">
      <div className="metricTop">
        <span>{title}</span>
        <span className="metricGlyph">
          {icon === "success" ? (
            <CheckCircle2 size={17} />
          ) : icon === "savings" ? (
            <ArrowDownRight size={17} />
          ) : (
            <BarChart3 size={17} />
          )}
        </span>
      </div>
      <strong>{value}</strong>
      <div className="metricFoot">
        <span>{foot}</span>
      </div>
    </article>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
