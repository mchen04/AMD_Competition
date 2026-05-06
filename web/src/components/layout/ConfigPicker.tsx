import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../state/AppContext";
import { Icon } from "../common/Icon";
import { ImportConfigDialog } from "./ImportConfigDialog";
import type { ConfigChoiceDTO } from "../../api/types";

export function ConfigPicker() {
  const { configs, loadConfigs, selectConfig } = useApp();
  const [open, setOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!ref.current) return;
      if (ref.current.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const all = useMemo(
    () => [...(configs?.bundled ?? []), ...(configs?.user ?? [])],
    [configs],
  );
  const current = all.find((c) => c.current) ?? null;
  const label = current?.label ?? "config";

  const onPick = async (choice: ConfigChoiceDTO) => {
    if (choice.current) {
      setOpen(false);
      return;
    }
    setBusyId(choice.path);
    setError(null);
    try {
      await selectConfig({ path: choice.path, source: choice.source });
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "switch failed");
    } finally {
      setBusyId(null);
    }
  };

  const onToggle = () => {
    if (!open) void loadConfigs();
    setOpen((o) => !o);
  };

  return (
    <>
      <div ref={ref} style={{ position: "relative" }}>
        <button className="provider-pill" onClick={onToggle} title={current?.path ?? ""}>
          <Icon name="folder" size={11} />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
          <span className="caret">
            <Icon name="chev" size={11} />
          </span>
        </button>
        {open && (
          <div className="dd-menu" style={{ minWidth: 320 }}>
            {!configs && <div className="dd-empty">loading…</div>}
            {configs && (
              <>
                {configs.bundled.length > 0 && (
                  <>
                    <div className="dd-section">Bundled</div>
                    {configs.bundled.map((c) => (
                      <ConfigRow key={c.path} c={c} busy={busyId === c.path} onPick={() => void onPick(c)} />
                    ))}
                  </>
                )}
                {configs.user.length > 0 && (
                  <>
                    <div className="dd-section">Imported</div>
                    {configs.user.map((c) => (
                      <ConfigRow key={c.path} c={c} busy={busyId === c.path} onPick={() => void onPick(c)} />
                    ))}
                  </>
                )}
                <div className="dd-divider" />
                <div
                  className="dd-item dd-action"
                  onClick={() => {
                    setOpen(false);
                    setImportOpen(true);
                  }}
                >
                  <span>
                    <Icon name="plus" size={13} />
                  </span>
                  <span>Import YAML…</span>
                </div>
                {error && <div className="dd-error">{error}</div>}
              </>
            )}
          </div>
        )}
      </div>
      {importOpen && <ImportConfigDialog onClose={() => setImportOpen(false)} />}
    </>
  );
}

function ConfigRow({ c, busy, onPick }: { c: ConfigChoiceDTO; busy: boolean; onPick: () => void }) {
  const meta = c.valid
    ? `${c.providers} provider${c.providers === 1 ? "" : "s"}${c.active ? ` · ${c.active}` : ""}`
    : "invalid";
  return (
    <div
      className={"dd-item" + (c.current ? " is-current" : "") + (busy ? " is-busy" : "")}
      onClick={onPick}
      title={c.path}
    >
      <span>
        <Icon name={c.source === "user" ? "file" : "folder"} size={13} />
      </span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{c.label}</span>
      <span className="meta">{busy ? "switching…" : meta}</span>
    </div>
  );
}
