
import { useEffect, useState, type FormEvent } from "react";
import "./App.css";

const API_URL = "http://localhost:8000";

type ReviewStatus = "suggested" | "confirmed" | "rejected";

type ReviewAction = "accept" | "edit" | "reject";

type MetadataField = {
  suggested_value: unknown;
  value: unknown;
  source: string | null;
  evidence: string | null;
  confidence: number;
  status: ReviewStatus;
};

type MetadataFieldName =
    | "title"
    | "description"
    | "creators"
    | "license"
    | "date_published"
    | "keywords"
    | "dataset_type"
    | "machine_learning_task"
    | "data_modality"
    | "language"
    | "number_of_records";

type Metadata = {
  title: MetadataField;
  description: MetadataField;
  creators: MetadataField;
  license: MetadataField;
  date_published: MetadataField;
  keywords: MetadataField;
  dataset_type: MetadataField;
  machine_learning_task: MetadataField;
  data_modality: MetadataField;
  language: MetadataField;
  number_of_records: MetadataField;
  splits: Record<string, unknown>;
  additional_information: MetadataField[];
  missing_information: string[];
};

type DatasetCandidate = {
  path: string;
  size: number;
  extension: string;
  sha?: string;
  confidence: string;
};

type Repository = {
  full_name: string;
  url: string;
  description: string | null;
  default_branch: string;
  selected_ref: string;
  commit_sha: string;
  license: string | null;
};

type Inventory = {
  total_files: number;
  metadata_files_found: number;
  metadata_files_read: number;
  dataset_candidates_found: number;
  dataset_candidates_returned: number;
};

type AnalysisResult = {
  repository: Repository;
  inventory: Inventory;
  dataset_candidates: DatasetCandidate[];
  warnings: string[];
};

type DatasetInspection = {
  path: string;
  size: number;
  format: string;
  encoding: string;
  delimiter: string;
  number_of_records: number;
  number_of_columns: number;
  columns: {
    name: string;
    inferred_type: string;
    missing_values: number;
  }[];
  sample_rows: Record<string, string>[];
};

type ExtractionResult = {
  repository: Repository;
  inventory: Inventory;
  selected_dataset: DatasetInspection;
  metadata: Metadata;
  dataset_candidates: DatasetCandidate[];
  warnings: string[];
};

type ConfirmationResult = {
  metadata: Metadata;
  confirmed: boolean;
  pending_fields: string[];
  rejected_fields: string[];
  can_generate_croissant: boolean;
};

type CroissantResult = {
  filename: string;
  format: string;
  validated: boolean;
  repository: string;
  commit_sha: string;
  selected_dataset: string;
  croissant: Record<string, unknown>;
};

const REQUIRED_FIELDS: MetadataFieldName[] = [
  "title",
  "description",
  "creators",
  "license",
  "date_published",
  "dataset_type",
  "data_modality",
];

const FIELD_LABELS: Record<MetadataFieldName, string> = {
  title: "Título",
  description: "Descrição",
  creators: "Criadores",
  license: "Licença",
  date_published: "Data de publicação",
  keywords: "Palavras-chave",
  dataset_type: "Tipo de dataset",
  machine_learning_task: "Tarefa de Machine Learning",
  data_modality: "Modalidade dos dados",
  language: "Idioma",
  number_of_records: "Número de registos",
};

function getTodayDate(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) {
    return true;
  }

  if (typeof value === "string") {
    return value.trim().length === 0;
  }

  if (Array.isArray(value)) {
    return value.length === 0;
  }

  if (typeof value === "object") {
    return Object.keys(value).length === 0;
  }

  return false;
}

function displayValue(value: unknown): string {
  if (isEmpty(value)) {
    return "Não identificado";
  }

  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(", ");
  }

  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }

  return String(value);
}

function fieldToInput(
    fieldName: MetadataFieldName,
    value: unknown,
): string {
  if (isEmpty(value)) {
    return "";
  }

  if (
      (fieldName === "creators" || fieldName === "keywords") &&
      Array.isArray(value)
  ) {
    return value.map((item) => String(item)).join("\n");
  }

  return typeof value === "string"
      ? value
      : JSON.stringify(value, null, 2);
}

function parseFieldInput(
    fieldName: MetadataFieldName,
    input: string,
): unknown {
  if (fieldName === "creators" || fieldName === "keywords") {
    return input
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);
  }

  return input.trim();
}

function getErrorMessage(data: any, fallback: string): string {
  if (typeof data?.detail === "string") {
    return data.detail;
  }

  if (data?.detail?.message) {
    const pending = data.detail.pending_fields;

    if (Array.isArray(pending) && pending.length > 0) {
      return `${data.detail.message} Campos pendentes: ${pending.join(", ")}.`;
    }

    return data.detail.message;
  }

  return fallback;
}

function App() {
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");

  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);

  const [selectedDatasetPath, setSelectedDatasetPath] = useState("");

  const [extraction, setExtraction] =
      useState<ExtractionResult | null>(null);

  const [editingValues, setEditingValues] =
      useState<Partial<Record<MetadataFieldName, string>>>({});

  const [confirmation, setConfirmation] =
      useState<ConfirmationResult | null>(null);

  const [croissant, setCroissant] =
      useState<CroissantResult | null>(null);

  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [loading, setLoading] = useState(false);
  const [busyField, setBusyField] =
      useState<MetadataFieldName | null>(null);

  const [ollamaAvailable, setOllamaAvailable] =
      useState<boolean | null>(null);

  const [modelInstalled, setModelInstalled] =
      useState<boolean | null>(null);

  const [configuredModel, setConfiguredModel] = useState("Ollama");

  // ==========================================================
  // OLLAMA STATUS
  // ==========================================================

  useEffect(() => {
    fetch(`${API_URL}/api/v1/ollama-status`)
        .then(async (response) => {
          const data = await response.json();

          setOllamaAvailable(data.available);
          setModelInstalled(data.model_installed);

          if (data.configured_model) {
            setConfiguredModel(data.configured_model);
          }
        })
        .catch(() => {
          setOllamaAvailable(false);
          setModelInstalled(false);
        });
  }, []);

  // ==========================================================
  // ANALYZE REPOSITORY
  // ==========================================================

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setLoading(true);
    setError("");
    setSuccessMessage("");

    setAnalysis(null);
    setExtraction(null);
    setConfirmation(null);
    setCroissant(null);
    setSelectedDatasetPath("");
    setEditingValues({});

    try {
      const response = await fetch(
          `${API_URL}/api/v1/analyze`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              url,
              ...(ref.trim() ? { ref: ref.trim() } : {}),
            }),
          },
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
            getErrorMessage(data, "Não foi possível analisar o repositório."),
        );
      }

      setAnalysis(data as AnalysisResult);

      if (data.dataset_candidates?.length > 0) {
        setSuccessMessage(
            `Repositório analisado. Foram encontrados ${data.dataset_candidates.length} candidatos a datasets.`,
        );
      } else {
        setSuccessMessage(
            "Repositório analisado, mas não foram encontrados datasets suportados.",
        );
      }
    } catch (err) {
      setError(
          err instanceof Error ? err.message : "Erro inesperado.",
      );
    } finally {
      setLoading(false);
    }
  }

  // ==========================================================
  // EXTRACT METADATA FROM SELECTED DATASET
  // ==========================================================

  async function extractDataset() {
    if (!selectedDatasetPath) {
      setError("Seleciona primeiro um dataset.");
      return;
    }

    if (!ollamaAvailable || !modelInstalled) {
      setError(
          "O Ollama ou o modelo configurado não estão disponíveis.",
      );
      return;
    }

    setLoading(true);
    setError("");
    setSuccessMessage("");

    setExtraction(null);
    setConfirmation(null);
    setCroissant(null);
    setEditingValues({});

    try {
      const response = await fetch(
          `${API_URL}/api/v1/extract-dataset`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              url,
              ...(ref.trim() ? { ref: ref.trim() } : {}),
              dataset_path: selectedDatasetPath,
            }),
          },
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
            getErrorMessage(data, "Não foi possível extrair os metadados."),
        );
      }

      setExtraction(data as ExtractionResult);

      setSuccessMessage(
          "Dataset inspecionado. Revê agora as sugestões de metadados.",
      );
    } catch (err) {
      setError(
          err instanceof Error ? err.message : "Erro inesperado.",
      );
    } finally {
      setLoading(false);
    }
  }

  // ==========================================================
  // REVIEW METADATA FIELD
  // ==========================================================


  async function reviewField(
      fieldName: MetadataFieldName,
      action: ReviewAction,
  ) {
    if (!extraction) {
      return;
    }

    const field = extraction.metadata[fieldName];

    let editedValue: unknown = undefined;

    if (action === "edit") {
      const input =
          editingValues[fieldName] ??
          fieldToInput(fieldName, field.value);

      editedValue = parseFieldInput(fieldName, input);

      if (
          fieldName === "date_published" &&
          typeof editedValue === "string" &&
          editedValue > getTodayDate()
      ) {
        setError("A data de publicação não pode ser posterior à data de hoje.");
        return;
      }

      if (isEmpty(editedValue)) {
        setError(
            `O campo "${FIELD_LABELS[fieldName]}" não pode ficar vazio.`,
        );
        return;
      }
    }

    setBusyField(fieldName);
    setError("");
    setSuccessMessage("");

    try {
      const review = {
        action,
        ...(action === "edit" ? { value: editedValue } : {}),
      };

      const response = await fetch(
          `${API_URL}/api/v1/metadata/confirm`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              metadata: extraction.metadata,
              reviews: {
                [fieldName]: review,
              },
            }),
          },
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (action === "edit" && response.status === 422) {
          setExtraction((previous) => {
            if (!previous) {
              return previous;
            }

            return {
              ...previous,
              metadata: {
                ...previous.metadata,
                [fieldName]: {
                  ...previous.metadata[fieldName],
                  value: editedValue,
                  status: "suggested",
                },
              },
            };
          });

          setConfirmation(null);
          setCroissant(null);
        }

        throw new Error(
            getErrorMessage(data, "Não foi possível guardar a revisão."),
        );
      }

      const result = data as ConfirmationResult;

      setExtraction((previous) => {
        if (!previous) {
          return previous;
        }

        return {
          ...previous,
          metadata: result.metadata,
        };
      });

      setConfirmation(result);

      setEditingValues((previous) => ({
        ...previous,
        [fieldName]: fieldToInput(
            fieldName,
            result.metadata[fieldName].value,
        ),
      }));

      setCroissant(null);

      if (action === "accept") {
        setSuccessMessage(
            `Sugestão de "${FIELD_LABELS[fieldName]}" confirmada.`,
        );
      } else if (action === "edit") {
        setSuccessMessage(
            `Campo "${FIELD_LABELS[fieldName]}" editado e confirmado.`,
        );
      } else {
        setSuccessMessage(
            `Campo "${FIELD_LABELS[fieldName]}" rejeitado. Terás de o preencher ou resolver antes de gerar Croissant.`,
        );
      }
    } catch (err) {
      setError(
          err instanceof Error ? err.message : "Erro inesperado.",
      );
    } finally {
      setBusyField(null);
    }
  }

  // ==========================================================
  // REQUIRED FIELD STATUS
  // ==========================================================

  function getPendingFields(): MetadataFieldName[] {
    if (!extraction) {
      return [...REQUIRED_FIELDS];
    }

    return REQUIRED_FIELDS.filter((fieldName) => {
      const field = extraction.metadata[fieldName];

      return (
          field.status !== "confirmed" ||
          isEmpty(field.value)
      );
    });
  }

  const pendingFields = getPendingFields();

  const canGenerateCroissant =
      extraction !== null &&
      pendingFields.length === 0 &&
      !loading &&
      busyField === null;

  // ==========================================================
  // GENERATE CROISSANT
  // ==========================================================

  async function generateCroissant() {
    if (!extraction || pendingFields.length > 0) {
      setError(
          "Confirma todos os campos obrigatórios antes de gerar Croissant.",
      );
      return;
    }

    setLoading(true);
    setError("");
    setSuccessMessage("");
    setCroissant(null);

    try {
      const response = await fetch(
          `${API_URL}/api/v1/croissant/generate`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              url,
              ...(ref.trim() ? { ref: ref.trim() } : {}),
              dataset_path: selectedDatasetPath,
              metadata: extraction.metadata,
            }),
          },
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
            getErrorMessage(data, "Não foi possível gerar o Croissant."),
        );
      }

      setCroissant(data as CroissantResult);

      setSuccessMessage(
          "Croissant gerado e validado com sucesso!",
      );
    } catch (err) {
      setError(
          err instanceof Error ? err.message : "Erro inesperado.",
      );
    } finally {
      setLoading(false);
    }
  }

  // ==========================================================
  // DOWNLOAD CROISSANT JSON-LD
  // ==========================================================

  function downloadCroissant() {
    if (!croissant) {
      return;
    }

    const json = JSON.stringify(
        croissant.croissant,
        null,
        2,
    );

    const blob = new Blob(
        [json],
        { type: "application/ld+json;charset=utf-8" },
    );

    const downloadUrl = URL.createObjectURL(blob);

    const link = document.createElement("a");

    link.href = downloadUrl;
    link.download = croissant.filename || "croissant.json";

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(downloadUrl);
  }

  // ==========================================================
  // METADATA FIELD RENDERING
  // ==========================================================

  function renderMetadataField(
      fieldName: MetadataFieldName,
      required = false,
  ) {
    if (!extraction) {
      return null;
    }

    const field = extraction.metadata[fieldName];

    if (!field) {
      return null;
    }

    const fieldBusy = busyField === fieldName;

    const inputValue =
        editingValues[fieldName] ??
        fieldToInput(fieldName, field.value);

    const hasSuggestion = !isEmpty(field.suggested_value);

    const statusLabel =
        field.status === "confirmed"
            ? "Confirmado"
            : field.status === "rejected"
                ? "Rejeitado"
                : "Por confirmar";

    const statusClass =
        field.status === "confirmed"
            ? "status-found"
            : field.status === "rejected"
                ? "status-missing"
                : "status-pending";

    return (
        <article
            className="metadata-field"
            key={fieldName}
        >
          <div className="field-header">
            <strong>
              {FIELD_LABELS[fieldName]}
              {required ? " *" : ""}
            </strong>

            <span className={statusClass}>
            {statusLabel}
          </span>
          </div>

          <p className="field-value">
            {displayValue(field.value)}
          </p>

          {field.source && (
              <p className="field-source">
                Fonte: {field.source}
              </p>
          )}

          {field.evidence && (
              <details>
                <summary>Ver evidência</summary>
                <p>{field.evidence}</p>
              </details>
          )}

          {!isEmpty(field.suggested_value) && (
              <details>
                <summary>Ver sugestão original da IA</summary>
                <p>
                  {displayValue(field.suggested_value)}
                </p>
              </details>
          )}

          {hasSuggestion && (
              <p className="field-confidence">
                Confiança estimada:{" "}
                {(field.confidence * 100).toFixed(0)}%
              </p>
          )}

          <label>
            {fieldName === "creators" || fieldName === "keywords"
                ? "Um valor por linha"
                : "Editar valor"}
          </label>

          {fieldName === "date_published" ? (
              <input
                  className="field-editor"
                  type="date"
                  max={getTodayDate()}
                  value={inputValue}
                  onChange={(event) =>
                      setEditingValues((previous) => ({
                        ...previous,
                        [fieldName]: event.target.value,
                      }))
                  }
                  disabled={fieldBusy || loading}
              />
          ) : (
              <textarea
                  className="field-editor"
                  rows={fieldName === "description" ? 4 : 2}
                  value={inputValue}
                  onChange={(event) =>
                      setEditingValues((previous) => ({
                        ...previous,
                        [fieldName]: event.target.value,
                      }))
                  }
                  placeholder={`Introduz ${FIELD_LABELS[fieldName].toLowerCase()}`}
                  disabled={fieldBusy || loading}
              />
          )}

          <div className="field-actions">
            <button
                type="button"
                onClick={() => void reviewField(fieldName, "accept")}
                disabled={
                    fieldBusy ||
                    loading ||
                    !hasSuggestion
                }
            >
              Aceitar sugestão
            </button>

            <button
                type="button"
                onClick={() => void reviewField(fieldName, "edit")}
                disabled={fieldBusy || loading}
            >
              Confirmar edição
            </button>

            <button
                type="button"
                onClick={() => void reviewField(fieldName, "reject")}
                disabled={fieldBusy || loading}
            >
              Rejeitar
            </button>
          </div>
        </article>
    );
  }

  // ==========================================================
  // USER INTERFACE
  // ==========================================================

  return (
      <main className="page">

        {/* HEADER */}

        <header className="hero">
          <p className="eyebrow">
            AI DATASET CURATION
          </p>

          <h1>Zenodo Metadata Assistant</h1>

          <p className="subtitle">
            Transforma repositórios GitHub em metadados
            estruturados para datasets de Machine Learning.
          </p>
        </header>

        {/* OLLAMA STATUS */}

        <section className="status-panel">
          <div>
            <span className="status-label">Ollama</span>

            <strong>
              {ollamaAvailable === null
                  ? "A verificar..."
                  : ollamaAvailable
                      ? "Disponível"
                      : "Indisponível"}
            </strong>
          </div>

          <div>
            <span className="status-label">{configuredModel}</span>

            <strong>
              {modelInstalled === null
                  ? "A verificar..."
                  : modelInstalled
                      ? "Instalado"
                      : "Não instalado"}
            </strong>
          </div>
        </section>

        {/* REPOSITORY FORM */}

        <section className="panel">
          <form onSubmit={analyze}>

            <label htmlFor="repo-url">
              URL do repositório GitHub
            </label>

            <input
                id="repo-url"
                type="url"
                placeholder="https://github.com/owner/repo"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
            />

            <label htmlFor="repo-ref">
              Branch, tag ou commit (opcional)
            </label>

            <input
                id="repo-ref"
                type="text"
                placeholder="Branch predefinida"
                value={ref}
                onChange={(event) => setRef(event.target.value)}
                maxLength={200}
            />

            <div className="form-footer">
              <p className="hint">
                Primeiro analisamos o repositório.
                Depois poderás escolher o dataset que pretendes utilizar.
              </p>

              <button
                  type="submit"
                  disabled={loading || !url.trim()}
              >
                {loading
                    ? "A analisar..."
                    : "Analisar repositório"}
              </button>
            </div>

          </form>
        </section>

        {/* MESSAGES */}

        {error && (
            <section className="message error">
              <strong>Ocorreu um erro</strong>
              <p>{error}</p>
            </section>
        )}

        {successMessage && (
            <section className="message success">
              <p>{successMessage}</p>
            </section>
        )}

        {/* REPOSITORY ANALYSIS */}

        {analysis && (
            <>
              <section className="panel">

                <p className="eyebrow">
                  REPOSITÓRIO ANALISADO
                </p>

                <h2>{analysis.repository.full_name}</h2>

                <p>
                  {analysis.repository.description ||
                      "Sem descrição no GitHub."}
                </p>

                <a
                    href={analysis.repository.url}
                    target="_blank"
                    rel="noreferrer"
                >
                  Abrir no GitHub ↗
                </a>

                <div className="details">
                  <span>Branch / referência</span>
                  <strong>{analysis.repository.selected_ref}</strong>

                  <span>Commit</span>
                  <strong className="hash">
                    {analysis.repository.commit_sha}
                  </strong>

                  <span>Licença GitHub</span>
                  <strong>
                    {analysis.repository.license || "Não identificada"}
                  </strong>
                </div>

              </section>

              {/* INVENTORY */}

              <section className="stats">

                <article className="stat">
                  <strong>{analysis.inventory.total_files}</strong>
                  <span>Ficheiros</span>
                </article>

                <article className="stat">
                  <strong>{analysis.inventory.metadata_files_read}</strong>
                  <span>Metadados lidos</span>
                </article>

                <article className="stat">
                  <strong>
                    {analysis.inventory.dataset_candidates_found}
                  </strong>
                  <span>Candidatos a datasets</span>
                </article>

              </section>

              {/* DATASET SELECTION */}

              <section className="panel">

                <p className="eyebrow">
                  DATASET SELECTION
                </p>

                <h2>Selecionar dataset</h2>

                <p className="hint">
                  Escolhe o ficheiro que pretendes inspecionar
                  e utilizar para gerar os metadados Croissant.
                </p>

                {analysis.dataset_candidates.length === 0 ? (
                    <p>
                      Não foram encontrados candidatos a datasets.
                    </p>
                ) : (
                    <>
                      <label htmlFor="dataset-select">
                        Dataset disponível
                      </label>

                      <select
                          id="dataset-select"
                          value={selectedDatasetPath}
                          onChange={(event) => {
                            setSelectedDatasetPath(event.target.value);
                            setExtraction(null);
                            setConfirmation(null);
                            setCroissant(null);
                          }}
                          disabled={loading}
                      >
                        <option value="">
                          Seleciona um ficheiro...
                        </option>

                        {analysis.dataset_candidates.map((file) => (
                            <option
                                key={file.path}
                                value={file.path}
                            >
                              {file.path} — {file.extension} —{" "}
                              {file.size.toLocaleString()} bytes
                            </option>
                        ))}
                      </select>

                      {selectedDatasetPath && (
                          <div className="form-footer">
                            <p className="hint">
                              O ficheiro será inspecionado antes da extração.
                            </p>

                            <button
                                type="button"
                                onClick={() => void extractDataset()}
                                disabled={
                                    loading ||
                                    !ollamaAvailable ||
                                    !modelInstalled
                                }
                            >
                              {loading
                                  ? "A inspecionar e extrair..."
                                  : "Inspecionar e extrair metadados"}
                            </button>
                          </div>
                      )}

                      {(!ollamaAvailable || !modelInstalled) && (
                          <p className="hint">
                            É necessário ter o Ollama e o modelo configurado
                            disponíveis para extrair metadados.
                          </p>
                      )}
                    </>
                )}

              </section>

              {/* ANALYSIS WARNINGS */}

              {analysis.warnings.length > 0 && (
                  <section className="message warning">
                    <h2>Avisos da análise</h2>

                    <ul>
                      {analysis.warnings.map((warning, index) => (
                          <li key={index}>{warning}</li>
                      ))}
                    </ul>
                  </section>
              )}
            </>
        )}

        {/* DATASET INSPECTION */}

        {extraction && (
            <>
              <section className="panel">

                <p className="eyebrow">
                  DATASET INSPECTION
                </p>

                <h2>Inspeção do dataset</h2>

                <p>
                  <strong>Ficheiro:</strong>{" "}
                  {extraction.selected_dataset.path}
                </p>

                <div className="details">
                  <span>Formato</span>
                  <strong>
                    {extraction.selected_dataset.format}
                  </strong>

                  <span>Tamanho</span>
                  <strong>
                    {extraction.selected_dataset.size.toLocaleString()} bytes
                  </strong>

                  <span>Codificação</span>
                  <strong>
                    {extraction.selected_dataset.encoding}
                  </strong>

                  <span>Delimitador</span>
                  <strong>
                    {JSON.stringify(extraction.selected_dataset.delimiter)}
                  </strong>

                  <span>Número de registos</span>
                  <strong>
                    {extraction.selected_dataset.number_of_records}
                  </strong>

                  <span>Número de colunas</span>
                  <strong>
                    {extraction.selected_dataset.number_of_columns}
                  </strong>
                </div>

                <h3>Colunas identificadas</h3>

                <ul className="file-list">
                  {extraction.selected_dataset.columns.map((column) => (
                      <li key={column.name}>
                        <strong>{column.name}</strong>

                        <span className="field-status">
                    {column.inferred_type} ·{" "}
                          {column.missing_values} valores em falta
                  </span>
                      </li>
                  ))}
                </ul>

              </section>

              {/* METADATA REVIEW */}

              <section className="panel">

                <p className="eyebrow">
                  HUMAN REVIEW
                </p>

                <h2>Revisão dos metadados</h2>

                <p className="hint">
                  A IA apresenta sugestões, mas és tu quem decide
                  quais os valores que ficam confirmados.
                  Podes aceitar, editar ou rejeitar cada campo.
                </p>

                <p className="hint">
                  Os campos assinalados com * são obrigatórios
                  para gerar o Croissant nesta aplicação.
                </p>

                <div className="metadata-grid">

                  {renderMetadataField("title", true)}

                  {renderMetadataField("description", true)}

                  {renderMetadataField("creators", true)}

                  {renderMetadataField("license", true)}

                  {renderMetadataField("date_published", true)}

                  {renderMetadataField("dataset_type", true)}

                  {renderMetadataField("data_modality", true)}

                  {renderMetadataField("keywords")}

                  {renderMetadataField("machine_learning_task")}

                  {renderMetadataField("language")}

                  {renderMetadataField("number_of_records")}

                </div>

              </section>

              {/* CONFIRMATION STATUS */}

              <section className="panel missing-panel">

                <p className="eyebrow">
                  CONFIRMATION STATUS
                </p>

                <h2>Estado da confirmação</h2>

                <p>
                  Campos obrigatórios confirmados:{" "}
                  <strong>
                    {REQUIRED_FIELDS.length - pendingFields.length}
                    {" / "}
                    {REQUIRED_FIELDS.length}
                  </strong>
                </p>

                {pendingFields.length === 0 ? (
                    <p className="status-found">
                      Todos os campos obrigatórios estão confirmados.
                    </p>
                ) : (
                    <>
                      <p>
                        Ainda precisas de resolver os seguintes campos:
                      </p>

                      <ul>
                        {pendingFields.map((field) => (
                            <li key={field}>
                              {FIELD_LABELS[field]}
                              {extraction.metadata[field].status === "rejected"
                                  ? " — rejeitado"
                                  : " — por confirmar"}
                            </li>
                        ))}
                      </ul>
                    </>
                )}

                {confirmation?.rejected_fields &&
                    confirmation.rejected_fields.length > 0 && (
                        <p>
                          Campos rejeitados:{" "}
                          {confirmation.rejected_fields
                              .map((field) => FIELD_LABELS[field as MetadataFieldName] || field)
                              .join(", ")}
                        </p>
                    )}

              </section>

              {/* CROISSANT GENERATION */}

              <section className="panel">

                <p className="eyebrow">
                  CROISSANT GENERATION
                </p>

                <h2>Gerar metadados Croissant</h2>

                <p className="hint">
                  O documento só pode ser gerado depois de confirmares
                  os sete campos obrigatórios. O backend volta a inspecionar
                  o dataset e valida o JSON-LD com mlcroissant.
                </p>

                <button
                    type="button"
                    onClick={() => void generateCroissant()}
                    disabled={!canGenerateCroissant}
                >
                  {loading
                      ? "A gerar Croissant..."
                      : "Gerar Croissant"}
                </button>

                {!canGenerateCroissant && (
                    <p className="hint">
                      Confirma todos os campos obrigatórios para ativar
                      a geração.
                    </p>
                )}

              </section>
            </>
        )}

        {/* CROISSANT RESULT */}

        {croissant && (
            <section className="panel">

              <p className="eyebrow">
                CROISSANT GENERATED
              </p>

              <h2>Croissant gerado com sucesso</h2>

              <p className="status-found">
                Documento validado com mlcroissant.
              </p>

              <div className="details">
                <span>Ficheiro</span>
                <strong>{croissant.filename}</strong>

                <span>Formato</span>
                <strong>{croissant.format}</strong>

                <span>Repositório</span>
                <strong>{croissant.repository}</strong>

                <span>Dataset</span>
                <strong>{croissant.selected_dataset}</strong>

                <span>Validação</span>
                <strong>
                  {croissant.validated ? "Aprovada" : "Não validado"}
                </strong>
              </div>

              <button
                  type="button"
                  onClick={downloadCroissant}
                  disabled={!croissant.validated}
              >
                Descarregar croissant.json
              </button>

              <h3>Pré-visualização JSON-LD</h3>

              <pre className="croissant-preview">
            {JSON.stringify(croissant.croissant, null, 2)}
          </pre>

            </section>
        )}

      </main>
  );
}

export default App;
