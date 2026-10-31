import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { apiClient, extractApiError } from "@/api/client";
import { useMe } from "@/api/hooks/auth";
import type { components } from "@/api/schema";

type Org = components["schemas"]["OrgSettings"];
type Template = components["schemas"]["TemplateOut"];
type Header = components["schemas"]["ExamHeader"];
type Role = components["schemas"]["Role"];
const emptyHeader: Header = {
  school_name: "",
  exam_title: "",
  subject_label: "",
  grade: "",
  date: "",
  duration_minutes: null,
  instructions: "",
};
const money = (value: string | number) => {
  const n = Number(value);
  return `$${n.toFixed(n < 1 ? 4 : 2)}`;
};

export function SettingsPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "organization";
  if (me?.role !== "admin") return <p>{t("admin.denied")}</p>;
  return (
    <section className="space-y-4 [&_button]:rounded [&_button]:border [&_button]:px-3 [&_button]:py-1 [&_input]:rounded [&_input]:border [&_input]:p-1 [&_label]:block [&_select]:rounded [&_select]:border [&_select]:p-1 [&_td]:p-2 [&_th]:p-2">
      <h1>{t("pages.settings.title")}</h1>
      <nav
        aria-label={t("pages.settings.title")}
        className="flex flex-wrap gap-4"
      >
        {["organization", "users", "templates", "costs"].map((key) => (
          <button
            key={key}
            type="button"
            aria-current={tab === key ? "page" : undefined}
            onClick={() => {
              setParams({ tab: key });
            }}
          >
            {t(`admin.${key}`)}
          </button>
        ))}
      </nav>
      {tab === "organization" && <Organization />}
      {tab === "users" && <Users />}
      {tab === "templates" && <Templates />}
      {tab === "costs" && <Costs />}
    </section>
  );
}
function Organization() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Org | null>(null);
  const [error, setError] = useState("");
  const org = useQuery({
    queryKey: ["org-settings"],
    queryFn: async () => (await apiClient.GET("/api/v1/org/settings")).data,
  });
  const models = useQuery({
    queryKey: ["models"],
    queryFn: async () => (await apiClient.GET("/api/v1/llm/models")).data,
  });
  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: async () => (await apiClient.GET("/api/v1/exam-templates")).data,
  });
  const value = draft ?? org.data;
  if (!value) return <p>{t("admin.loading")}</p>;
  const update = (patch: Partial<Org>) => {
    setDraft({ ...value, ...patch });
  };
  const model = models.data?.find((m) => m.id === value.extract_model);
  const pageCost = model
    ? (Number(model.price_in_per_m) * 1200 +
        Number(model.price_out_per_m) * 2500) /
      1000000
    : 0;
  return (
    <form
      className="grid max-w-xl gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        void (async () => {
          const r = await apiClient.PATCH("/api/v1/org/settings", {
            body: value,
          });
          if (!r.response.ok)
            setError(extractApiError(r.response.status, r.error).message);
          else {
            setError("");
            setDraft(null);
            await qc.invalidateQueries({ queryKey: ["org-settings"] });
          }
        })();
      }}
    >
      <label>
        {t("admin.name")}
        <input
          required
          value={value.name}
          onChange={(e) => {
            update({ name: e.target.value });
          }}
        />
      </label>
      <label>
        {t("admin.digits")}
        <select
          value={value.default_digits}
          onChange={(e) => {
            update({ default_digits: e.target.value as Org["default_digits"] });
          }}
        >
          <option value="arabic">{t("admin.arabic")}</option>
          <option value="western">{t("admin.western")}</option>
        </select>
      </label>
      <label>
        {t("admin.defaultTemplate")}
        <select
          value={value.default_template_id ?? ""}
          onChange={(e) => {
            update({ default_template_id: e.target.value || null });
          }}
        >
          <option value="">—</option>
          {templates.data?.items.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("admin.model")}
        <select
          value={value.extract_model}
          onChange={(e) => {
            update({ extract_model: e.target.value });
          }}
        >
          {models.data?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.id} ({money(m.price_in_per_m)} / {money(m.price_out_per_m)} /
              1M)
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("admin.verify")}
        <select
          value={value.verify_policy}
          onChange={(e) => {
            update({ verify_policy: e.target.value as Org["verify_policy"] });
          }}
        >
          {(["off", "low_confidence", "all"] as const).map((x) => (
            <option key={x} value={x}>
              {t(`admin.${x}`)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("admin.cap")}
        <input
          type="number"
          min="0"
          step="0.01"
          value={value.llm_monthly_cap_usd ?? ""}
          onChange={(e) => {
            update({
              llm_monthly_cap_usd:
                e.target.value === "" ? null : Number(e.target.value),
            });
          }}
        />
      </label>
      <p>
        {t("admin.pageEstimate", {
          count:
            pageCost && value.llm_monthly_cap_usd
              ? Math.floor(value.llm_monthly_cap_usd / pageCost)
              : 0,
        })}
      </p>
      <button type="submit">{t("admin.save")}</button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
function Users() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState("");
  const [error, setError] = useState("");
  const [role, setRole] = useState<Role>("teacher");
  const users = useQuery({
    queryKey: ["users"],
    queryFn: async () => (await apiClient.GET("/api/v1/users")).data,
  });
  const refresh = async () => qc.invalidateQueries({ queryKey: ["users"] });
  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void (async () => {
            const r = await apiClient.POST("/api/v1/users", {
              body: { name, email, password, role },
            });
            if (!r.response.ok)
              setError(extractApiError(r.response.status, r.error).message);
            else {
              setShown(password);
              setPassword("");
              setError("");
              await refresh();
            }
          })();
        }}
      >
        <label>
          {t("admin.name")}
          <input
            required
            value={name}
            onChange={(e) => {
              setName(e.target.value);
            }}
          />
        </label>
        <label>
          {t("admin.email")}
          <input
            required
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
            }}
          />
        </label>
        <label>
          {t("admin.password")}
          <input
            required
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
          />
        </label>
        <label>
          {t("admin.role")}
          <select
            value={role}
            onChange={(e) => {
              setRole(e.target.value as Role);
            }}
          >
            {(["admin", "editor", "teacher"] as const).map((x) => (
              <option key={x} value={x}>
                {t(`admin.role_${x}`)}
              </option>
            ))}
          </select>
        </label>
        <button>{t("admin.invite")}</button>
      </form>
      {shown && (
        <p>
          {shown}{" "}
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard.writeText(shown);
            }}
          >
            {t("admin.copy")}
          </button>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <table>
        <thead>
          <tr>
            {["name", "email", "role", "active", "lastLogin"].map((x) => (
              <th key={x}>{t(`admin.${x}`)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {users.data?.items.map((u) => (
            <tr key={u.id}>
              <td>{u.name}</td>
              <td>{u.email}</td>
              <td>
                <select
                  aria-label={`${t("admin.role")} ${u.name}`}
                  value={u.role}
                  onChange={(e) => {
                    void (async () => {
                      const r = await apiClient.PATCH("/api/v1/users/{id}", {
                        params: { path: { id: u.id } },
                        body: { role: e.target.value as Role },
                      });
                      if (!r.response.ok)
                        setError(
                          extractApiError(r.response.status, r.error).message,
                        );
                      else {
                        setError("");
                        await refresh();
                      }
                    })();
                  }}
                >
                  {(["admin", "editor", "teacher"] as const).map((x) => (
                    <option key={x} value={x}>
                      {t(`admin.role_${x}`)}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                {t(u.is_active ? "admin.yes" : "admin.no")}{" "}
                {u.is_active && (
                  <button
                    type="button"
                    onClick={() => {
                      void (async () => {
                        const r = await apiClient.PATCH("/api/v1/users/{id}", {
                          params: { path: { id: u.id } },
                          body: { is_active: false },
                        });
                        if (!r.response.ok)
                          setError(
                            extractApiError(r.response.status, r.error).message,
                          );
                        else await refresh();
                      })();
                    }}
                  >
                    {t("admin.deactivate")}
                  </button>
                )}
              </td>
              <td>{u.last_login_at ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Templates() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Template | null>(null);
  const [name, setName] = useState("");
  const [header, setHeader] = useState<Header>(emptyHeader);
  const [error, setError] = useState("");
  const list = useQuery({
    queryKey: ["templates"],
    queryFn: async () => (await apiClient.GET("/api/v1/exam-templates")).data,
  });
  const refresh = async () => qc.invalidateQueries({ queryKey: ["templates"] });
  return (
    <div className="space-y-4">
      <ul>
        {list.data?.items.map((x) => (
          <li key={x.id}>
            <button
              type="button"
              onClick={() => {
                setSelected(x);
                setName(x.name);
                setHeader(x.header);
              }}
            >
              {x.name}
            </button>{" "}
            <button
              type="button"
              onClick={() => {
                void (async () => {
                  await apiClient.DELETE("/api/v1/exam-templates/{id}", {
                    params: { path: { id: x.id } },
                  });
                  await refresh();
                })();
              }}
            >
              {t("admin.delete")}
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => {
          setSelected(null);
          setName("");
          setHeader(emptyHeader);
        }}
      >
        {t("admin.newTemplate")}
      </button>
      <form
        className="grid max-w-xl gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void (async () => {
            const r = selected
              ? await apiClient.PATCH("/api/v1/exam-templates/{id}", {
                  params: { path: { id: selected.id } },
                  body: { name, header },
                })
              : await apiClient.POST("/api/v1/exam-templates", {
                  body: { name, header },
                });
            if (!r.response.ok)
              setError(extractApiError(r.response.status, r.error).message);
            else if (r.data) {
              setSelected(r.data);
              setError("");
              await refresh();
            }
          })();
        }}
      >
        <label>
          {t("admin.name")}
          <input
            required
            value={name}
            onChange={(e) => {
              setName(e.target.value);
            }}
          />
        </label>
        {(
          [
            "school_name",
            "exam_title",
            "subject_label",
            "grade",
            "date",
            "instructions",
          ] as const
        ).map((k) => (
          <label key={k}>
            {t(`admin.${k}`)}
            <input
              value={header[k]}
              onChange={(e) => {
                setHeader({ ...header, [k]: e.target.value });
              }}
            />
          </label>
        ))}
        <label>
          {t("admin.duration")}
          <input
            type="number"
            min="1"
            max="1000"
            value={header.duration_minutes ?? ""}
            onChange={(e) => {
              setHeader({
                ...header,
                duration_minutes: e.target.value
                  ? Number(e.target.value)
                  : null,
              });
            }}
          />
        </label>
        <button>{t("admin.save")}</button>
      </form>
      {selected && (
        <label>
          {t("admin.logo")}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file)
                void (async () => {
                  const r = await apiClient.POST(
                    "/api/v1/exam-templates/{id}/logo",
                    {
                      params: { path: { id: selected.id } },
                      body: { file: file.name },
                      bodySerializer() {
                        const data = new FormData();
                        data.set("file", file);
                        return data;
                      },
                    },
                  );
                  if (r.data) {
                    setSelected(r.data);
                    await refresh();
                  } else
                    setError(
                      extractApiError(r.response.status, r.error).message,
                    );
                })();
            }}
          />
        </label>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="border p-4">
        <h2>{t("admin.preview")}</h2>
        {selected?.logo_asset_id && (
          <img
            className="max-w-32"
            src={`/api/v1/assets/${selected.logo_asset_id}/image`}
            alt={t("admin.logo")}
          />
        )}
        <p>{header.school_name}</p>
        <p>{header.exam_title}</p>
        <p>
          {header.subject_label} {header.grade} {header.date}{" "}
          {header.duration_minutes}
        </p>
        <p>{header.instructions}</p>
      </div>
    </div>
  );
}
function Costs() {
  const { t } = useTranslation();
  const costs = useQuery({
    queryKey: ["costs"],
    queryFn: async () =>
      (
        await apiClient.GET("/api/v1/costs/summary", {
          params: { query: { months: 6 } },
        })
      ).data,
  });
  const c = costs.data;
  if (!c) return <p>{t("admin.loading")}</p>;
  const max = Math.max(...c.by_month.map((x) => Number(x.cost_usd)), 0.00001);
  return (
    <div className="space-y-4">
      <p>
        {t("admin.thisMonth")}: {money(c.this_month_usd)} /{" "}
        {c.cap_usd == null ? "—" : money(c.cap_usd)}
      </p>
      {c.cap_usd != null && (
        <progress
          max={c.cap_usd || 1}
          value={Number(c.this_month_usd)}
          aria-label={t("admin.cap")}
        />
      )}
      <p>
        {t("admin.total")}: {money(c.total_usd)}
      </p>
      <p>
        {t("admin.average")}: {money(c.average_cost_per_page)}
      </p>
      <h2>{t("admin.byMonth")}</h2>
      <svg
        role="img"
        aria-label={t("admin.byMonth")}
        viewBox={`0 0 ${String(c.by_month.length * 100)} 150`}
      >
        <text x="0" y="12" fontSize="10">
          {money(max)}
        </text>
        <text x="0" y="118" fontSize="10">
          $0
        </text>
        <line
          x1="0"
          y1="120"
          x2={c.by_month.length * 100}
          y2="120"
          stroke="currentColor"
        />
        {c.by_month.map((x, i) => (
          <g key={x.name}>
            <rect
              x={i * 100 + 15}
              y={120 - (100 * Number(x.cost_usd)) / max}
              width="50"
              height={(100 * Number(x.cost_usd)) / max}
              fill="currentColor"
            />
            <text x={i * 100 + 5} y="140" fontSize="12">
              {x.name}
            </text>
          </g>
        ))}
      </svg>
      <CostTable rows={c.by_month} />
      <h2>{t("admin.byStage")}</h2>
      <CostTable rows={c.by_stage} />
      <h2>{t("admin.byModel")}</h2>
      <CostTable rows={c.by_model} />
      <h2>{t("admin.topSources")}</h2>
      <table>
        <thead>
          <tr>
            <th>{t("admin.name")}</th>
            <th>{t("admin.cost")}</th>
            <th>{t("admin.pages")}</th>
            <th>{t("admin.average")}</th>
          </tr>
        </thead>
        <tbody>
          {c.top_sources.map((x) => (
            <tr key={x.source_id}>
              <th>{x.title}</th>
              <td>{money(x.cost_usd)}</td>
              <td>{x.pages}</td>
              <td>{money(x.cost_per_page)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function CostTable({ rows }: { rows: components["schemas"]["CostGroup"][] }) {
  const { t } = useTranslation();
  return (
    <table>
      <thead>
        <tr>
          <th>{t("admin.name")}</th>
          <th>{t("admin.cost")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((x) => (
          <tr key={x.name}>
            <th>{x.name}</th>
            <td>{money(x.cost_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
