import { useCallback, useEffect, useRef, useState } from "react";
import { useApp } from "../../state/AppContext";
import { Icon } from "../common/Icon";

interface Props {
  onClose: () => void;
}

const NAME_HINT = "alphanumeric, . _ -, ending in .yaml or .yml";

export function ImportConfigDialog({ onClose }: Props) {
  const { importConfig } = useApp();
  const [name, setName] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [selectAfter, setSelectAfter] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handleFile = useCallback((file: File) => {
    if (!name) {
      const safe = file.name.replace(/[^A-Za-z0-9._-]/g, "-");
      setName(safe.endsWith(".yaml") || safe.endsWith(".yml") ? safe : `${safe}.yaml`);
    }
    const reader = new FileReader();
    reader.onload = () => setYamlText(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => setError("could not read file");
    reader.readAsText(file);
  }, [name]);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const onSubmit = async () => {
    setError(null);
    if (!name.trim()) {
      setError("name is required");
      return;
    }
    if (!yamlText.trim()) {
      setError("paste or upload a YAML body");
      return;
    }
    setBusy(true);
    try {
      await importConfig({
        name: name.trim(),
        yaml: yamlText,
        overwrite,
        select: selectAfter,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className="modal-card"
        onMouseDown={(e) => e.stopPropagation()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
      >
        <div className="modal-head">
          <div className="modal-title">
            <Icon name="upload" size={14} />
            <span>Import config YAML</span>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="close">
            <Icon name="x" size={14} />
          </button>
        </div>
        <div className="modal-body">
          <label className="modal-label">name</label>
          <input
            className="modal-input"
            type="text"
            placeholder="my-cluster.yaml"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <div className="modal-hint">{NAME_HINT}</div>

          <label className="modal-label" style={{ marginTop: 12 }}>
            yaml
          </label>
          <textarea
            className="modal-textarea"
            spellCheck={false}
            value={yamlText}
            onChange={(e) => setYamlText(e.target.value)}
            placeholder="paste a full rocm-doctor config here, or drop a .yaml file onto this dialog"
            rows={14}
          />
          <div className="modal-row">
            <button
              className="topbar-btn"
              onClick={() => fileInputRef.current?.click()}
              type="button"
            >
              <Icon name="upload" size={12} /> upload file
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".yaml,.yml,text/yaml"
              onChange={onFileChange}
              style={{ display: "none" }}
            />
            <label className="modal-check">
              <input
                type="checkbox"
                checked={overwrite}
                onChange={(e) => setOverwrite(e.target.checked)}
              />
              overwrite if exists
            </label>
            <label className="modal-check">
              <input
                type="checkbox"
                checked={selectAfter}
                onChange={(e) => setSelectAfter(e.target.checked)}
              />
              switch to it after import
            </label>
          </div>
          {error && <div className="modal-error">{error}</div>}
        </div>
        <div className="modal-foot">
          <button className="topbar-btn" onClick={onClose} disabled={busy}>
            cancel
          </button>
          <button className="topbar-btn primary" onClick={() => void onSubmit()} disabled={busy}>
            {busy ? "importing…" : "import"}
          </button>
        </div>
      </div>
    </div>
  );
}
