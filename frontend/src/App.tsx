
import { useEffect, useState, type FormEvent } from "react";
import "./App.css";

const API_URL = "http://localhost:8000";

type ReviewStatus = "suggested" | "confirmed" | "rejected";

type MetadataField = {
  suggested_value: unknown;
  value: unknown;
  source: string | null;
  evidence: string | null;
  confidence: number;
  status: ReviewStatus;
};

type Metadata = {
  title: MetadataField;
  description: MetadataField;
  creators: MetadataField;
  license: MetadataField;
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
  confidence: string;
  sha?: string;
};

type RepositoryResponse = {
  repository: {
    full_name: string;
    url: string;
    description: string | null;
    default_branch: string;
    selected_ref: string;
    commit_sha: string;
    license: string | null;
  };
  inventory: {
    total_files: number;
    metadata_files_found: number;
    metadata_files_read: number;
    dataset_candidates_found: number;
    dataset_candidates_returned: number;
  };
  dataset_candidates: DatasetCandidate[];
  warnings: string[];
};

type ExtractionResponse = {
  repository: RepositoryResponse["repository"];
  inventory: RepositoryResponse["inventory"];
  selected_dataset: {
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
  metadata: Metadata;
  dataset_candidates: DatasetCandidate[];
  warnings: string[];
};

type FieldReview = {
  action: "accept" | "edit" | "reject";
  value?: unknown;
};

type ConfirmationResponse = {
  metadata: Metadata;
  confirmed: boolean;
  pending_fields: string[];
  rejected_fields: string[];
  can_generate_croissant: boolean;
};

const FIELD_CONFIG: {
  key: keyof Pick<
      Metadata,
      | "title"
      | "description"
      | "creators"
      | "license"
      | "keywords"
      | "dataset_type"
      | "machine_learning_task"
      | "data_modality"
      | "language"
      | "number_of_records"
  >;
  label: string;
  required: boolean;
  multiline?: boolean;
  list?: boolean;
}[] = [
  { key: "title", label: "Título", required: true },
  {
    key: "description",
    label: "Descrição",
    required: true,
    multiline: true,
  },
  {
    key: "creators",
    label: "Criadores",
    required: true,
    multiline: true,
    list: true,
  },
  { key: "license", label: "Licença", required: true },
  {
    key: "keywords",
    label: "Palavras-chave",
    required: false,
    multiline: true,
    list: true,
  },
  { key: "dataset_type", label: "Tipo de dataset", required: true },
  {
    key: "machine_learning_task",
    label: "Tarefa de Machine Learning",
    required: false,
  },
  {
    key: "data_modality",
    label: "Modalidade dos dados",
    required: true,
  },
  { key: "language", label: "Idioma", required: false },
  {
    key: "number_of_records",
    label: "Número de registos",
    required: false,
  },
];

function getFieldText(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }

  if (Array.isArray(value)) {
    return value
        .map((item) => {
          if (typeof item === "string") return item;
          return JSON.stringify(item);
        })
        .join("\n");
  }

  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }

  return String(value);
}

function parseFieldValue(
    text: string,
    field: (typeof FIELD_CONFIG)[number],
): unknown {
  if (field.list) {
    return text
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean);
  }

  if (field.key === "number_of_records") {
    const number = Number(text);

    if (!Number.isFinite(number) || number < 0) {
      throw new Error("Introduz um número válido de registos.");
    }

    return number;
  }

  return text.trim();
}

function hasValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function statusLabel(status: ReviewStatus): string {
  if (status === "confirmed") return "Confirmado";
  if (status === "rejected") return "Rejeitado";
  return "Por rever";
}

function StatusBadge({ status }: { status: ReviewStatus }) {
  return (
      <span className={`review-badge ${status}`}>
      {statusLabel(status)}
    </span>
  );
}

function App() {
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");

  const [repositoryResult, setRepositoryResult] =
      useState<RepositoryResponse | null>(null);

  const [selectedDatasetPath, setSelectedDatasetPath] = useState("");

  const [extraction, setExtraction] =
      useState<ExtractionResponse | null>(null);

  const [reviews, setReviews] = useState<Record<string, FieldReview>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const [confirmation, setConfirmation] =
      useState<ConfirmationResponse | null>(null);

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reviewLoading, setReviewLoading] = useState<string | null>(null);

  const [ollamaAvailable, setOllamaAvailable] =
      useState<boolean | null>(null);

  const [modelInstalled, setModelInstalled] =
      useState<boolean | null>(null);

  const [configuredModel, setConfiguredModel] = useState("Ollama");

  useEffect(() => {
    fetch(`${API_URL}/api/v1/ollama-status`)
        .then((response) => {
          if (!response.ok) throw new Error("Erro ao consultar Ollama");
          return response.json();
        })
        .then((data) => {
          setOllamaAvailable(data.available);
          setModelInstalled(data.model_installed);
          setConfiguredModel(data.configured_model || "Ollama");
        })
        .catch(() => {
          setOllamaAvailable(false);
          setModelInstalled(false);
        });
  }, []);

  async function requestJson<T>(
      endpoint: string,
      body?: unknown,
  ): Promise<T> {
    const response = await fetch(`${API_URL}${endpoint}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined
          ? undefined
          : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
          typeof data.detail === "string"
              ? data.detail
              : `Erro na comunicação com o servidor (${response.status}).`,
      );
    }

    return data as T;
  }

  async function analyzeRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setLoading(true);
    setError("");
    setRepositoryResult(null);
    setExtraction(null);
    setConfirmation(null);
    setReviews({});
    setDrafts({});
    setSelectedDatasetPath("");

    try {
      const data = await requestJson<RepositoryResponse>(
          "/api/v1/analyze",
          {
            url: url.trim(),
            ...(ref.trim() ? { ref: ref.trim() } : {}),
          },
      );

      setRepositoryResult(data);

      if (data.dataset_candidates.length === 0) {
        setError("Não foram encontrados candidatos a datasets.");
      }
    } catch (err) {
      setError(
          err instanceof Error ? err.message : "Erro inesperado na análise.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function extractSelectedDataset() {
    if (!selectedDatasetPath) {
      setError("Seleciona primeiro um dataset.");
      return;
    }

    setLoading(true);
    setError("");
    setExtraction(null);
    setConfirmation(null);
    setReviews({});
    setDrafts({});

    try {
      const data = await requestJson<ExtractionResponse>(
          "/api/v1/extract-dataset",
          {
            url: url.trim(),
            ...(ref.trim() ? { ref: ref.trim() } : {}),
            dataset_path: selectedDatasetPath,
          },
      );

      setExtraction(data);

      const initialDrafts: Record<string, string> = {};

      for (const field of FIELD_CONFIG) {
        const metadataField = data.metadata[field.key] as MetadataField;
        const initialValue =
            metadataField.value ?? metadataField.suggested_value;

        initialDrafts[field.key] = getFieldText(initialValue);
      }

      setDrafts(initialDrafts);
    } catch (err) {
      setError(
          err instanceof Error ? err.message : "Erro na extração dos metadados.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function submitReview(
      fieldName: string,
      review: FieldReview,
  ) {
    if (!extraction) return;

    setReviewLoading(fieldName);
    setError("");

    const updatedReviews = {
      ...reviews,
      [fieldName]: review,
    };

    try {
      const data = await requestJson<ConfirmationResponse>(
          "/api/v1/metadata/confirm",
          {
            metadata: extraction.metadata,
            reviews: updatedReviews,
          },
      );

      setReviews(updatedReviews);

      setExtraction((previous) =>
          previous
              ? { ...previous, metadata: data.metadata }
              : previous,
      );

      setConfirmation(data);

      const updatedDrafts = { ...drafts };
      for (const field of FIELD_CONFIG) {
        const metadataField = data.metadata[field.key] as MetadataField;
        const value = metadataField.value ?? metadataField.suggested_value;
        updatedDrafts[field.key] = getFieldText(value);
      }
      setDrafts(updatedDrafts);
    } catch (err) {
      setError(
          err instanceof Error ? err.message : "Não foi possível guardar a revisão.",
      );
    } finally {
      setReviewLoading(null);
    }
  }

  async function acceptSuggestion(fieldName: string) {
    await submitReview(fieldName, { action: "accept" });
  }

  async function rejectSuggestion(fieldName: string) {
    await submitReview(fieldName, { action: "reject" });
  }

  async function editAndConfirm(field: (typeof FIELD_CONFIG)[number]) {
    const text = drafts[field.key] ?? "";

    try {
      const value = parseFieldValue(text, field);

      if (!hasValue(value)) {
        setError(`O campo "${field.label}" não pode ficar vazio.`);
        return;
      }

      await submitReview(field.key, {
        action: "edit",
        value,
      });
    } catch (err) {
      setError(
          err instanceof Error ? err.message : "Valor inválido.",
      );
    }
  }

  const pendingFields =
      confirmation?.pending_fields ??
      extraction?.metadata.missing_information ??
      [];

  const confirmedCount = extraction
      ? FIELD_CONFIG.filter((field) => {
        const metadataField = extraction.metadata[field.key] as MetadataField;
        return metadataField.status === "confirmed";
      }).length
      : 0;

  return (
      <main className="page">
        <header className="hero">
          <p className="eyebrow">AI DATASET CURATION</p>
          <h1>Zenodo Metadata Assistant</h1>
          <p className="subtitle">
            Transforma repositórios GitHub em metadados estruturados
            para datasets de Machine Learning.
          </p>
        </header>

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
            <span className="status-label">Modelo configurado</span>
            <strong>{configuredModel}</strong>
          </div>

          <div>
            <span className="status-label">Estado do modelo</span>
            <strong>
              {modelInstalled === null
                  ? "A verificar..."
                  : modelInstalled
                      ? "Instalado"
                      : "Não instalado"}
            </strong>
          </div>
        </section>

        <section className="panel">
          <form onSubmit={analyzeRepository}>
            <h2>1. Analisar repositório</h2>

            <label htmlFor="repo-url">URL do repositório GitHub</label>
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
                Primeiro identificamos os ficheiros e os datasets disponíveis.
              </p>

              <button
                  type="submit"
                  disabled={
                      loading ||
                      !ollamaAvailable ||
                      !modelInstalled ||
                      !url.trim()
                  }
              >
                {loading ? "A analisar..." : "Analisar repositório"}
              </button>
            </div>
          </form>
        </section>

        {error && (
            <section className="message error">
              <strong>Ocorreu um problema</strong>
              <p>{error}</p>
            </section>
        )}

        {repositoryResult && (
            <>
              <section className="panel">
                <p className="eyebrow">REPOSITÓRIO ANALISADO</p>
                <h2>{repositoryResult.repository.full_name}</h2>

                <p>{repositoryResult.repository.description}</p>

                <a
                    href={repositoryResult.repository.url}
                    target="_blank"
                    rel="noreferrer"
                >
                  Abrir no GitHub ↗
                </a>

                <div className="details">
                  <span>Branch</span>
                  <strong>{repositoryResult.repository.selected_ref}</strong>

                  <span>Commit</span>
                  <strong className="hash">
                    {repositoryResult.repository.commit_sha}
                  </strong>

                  <span>Licença GitHub</span>
                  <strong>
                    {repositoryResult.repository.license || "Não identificada"}
                  </strong>
                </div>
              </section>

              <section className="stats">
                <article className="stat">
                  <strong>{repositoryResult.inventory.total_files}</strong>
                  <span>Ficheiros</span>
                </article>

                <article className="stat">
                  <strong>{repositoryResult.inventory.metadata_files_read}</strong>
                  <span>Metadados lidos</span>
                </article>

                <article className="stat">
                  <strong>
                    {repositoryResult.inventory.dataset_candidates_found}
                  </strong>
                  <span>Candidatos a datasets</span>
                </article>
              </section>

              <section className="panel">
                <p className="eyebrow">DATASET SELECTION</p>
                <h2>2. Selecionar dataset</h2>

                <p className="hint">
                  Escolhe o ficheiro que queres inspecionar e descrever.
                </p>

                <div className="dataset-list">
                  {repositoryResult.dataset_candidates.map((dataset) => (
                      <label
                          className={`dataset-option ${
                              selectedDatasetPath === dataset.path ? "selected" : ""
                          }`}
                          key={dataset.path}
                      >
                        <input
                            type="radio"
                            name="dataset"
                            value={dataset.path}
                            checked={selectedDatasetPath === dataset.path}
                            onChange={() => setSelectedDatasetPath(dataset.path)}
                        />

                        <span className="dataset-option-content">
                    <strong>{dataset.path}</strong>
                    <small>
                      {dataset.extension} ·{" "}
                      {dataset.size.toLocaleString()} bytes ·{" "}
                      Confiança: {dataset.confidence}
                    </small>
                  </span>
                      </label>
                  ))}
                </div>

                <div className="form-footer">
                  <p className="hint">
                    A extração é feita apenas para o dataset selecionado.
                  </p>

                  <button
                      type="button"
                      disabled={loading || !selectedDatasetPath}
                      onClick={extractSelectedDataset}
                  >
                    {loading ? "A extrair..." : "Inspecionar e extrair metadados"}
                  </button>
                </div>
              </section>
            </>
        )}

        {extraction && (
            <>
              <section className="panel">
                <p className="eyebrow">SELECTED DATASET</p>
                <h2>Dataset selecionado</h2>

                <div className="details">
                  <span>Ficheiro</span>
                  <strong>{extraction.selected_dataset.path}</strong>

                  <span>Formato</span>
                  <strong>{extraction.selected_dataset.format}</strong>

                  <span>Registos</span>
                  <strong>{extraction.selected_dataset.number_of_records}</strong>

                  <span>Colunas</span>
                  <strong>{extraction.selected_dataset.number_of_columns}</strong>

                  <span>Codificação</span>
                  <strong>{extraction.selected_dataset.encoding}</strong>
                </div>

                <h3>Estrutura das colunas</h3>
                <div className="table-wrapper">
                  <table className="inspection-table">
                    <thead>
                    <tr>
                      <th>Coluna</th>
                      <th>Tipo</th>
                      <th>Valores em falta</th>
                    </tr>
                    </thead>
                    <tbody>
                    {extraction.selected_dataset.columns.map((column) => (
                        <tr key={column.name}>
                          <td>{column.name}</td>
                          <td>{column.inferred_type}</td>
                          <td>{column.missing_values}</td>
                        </tr>
                    ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="panel">
                <p className="eyebrow">HUMAN METADATA REVIEW</p>
                <h2>3. Rever metadados</h2>

                <p className="hint">
                  Analisa as sugestões, consulta as evidências e decide
                  se queres aceitar, editar ou rejeitar cada valor.
                  Nenhuma sugestão é confirmada automaticamente.
                </p>

                <div className="review-progress">
                  <div>
                    <strong>{confirmedCount} / {FIELD_CONFIG.length}</strong>
                    <span>Campos confirmados</span>
                  </div>
                  <div>
                    <strong>{pendingFields.length}</strong>
                    <span>Campos obrigatórios pendentes</span>
                  </div>
                </div>

                <div className="metadata-grid">
                  {FIELD_CONFIG.map((field) => {
                    const metadataField =
                        extraction.metadata[field.key] as MetadataField;

                    const suggestion = metadataField.suggested_value;
                    const currentValue = metadataField.value;

                    const hasSuggestion = hasValue(suggestion);
                    const isConfirmed = metadataField.status === "confirmed";

                    return (
                        <article className="metadata-field review-card" key={field.key}>
                          <div className="field-header">
                            <strong>{field.label}</strong>
                            <StatusBadge status={metadataField.status} />
                          </div>

                          {field.required && (
                              <span className="required-label">
                        Campo obrigatório
                      </span>
                          )}

                          <div className="suggestion-box">
                      <span className="field-label">
                        {isConfirmed ? "Valor confirmado" : "Sugestão da IA"}
                      </span>

                            <p className="field-value">
                              {hasValue(currentValue)
                                  ? getFieldText(currentValue)
                                  : "Não identificado"}
                            </p>
                          </div>

                          {metadataField.source && (
                              <p className="field-source">
                                Fonte: {metadataField.source}
                              </p>
                          )}

                          {metadataField.evidence && (
                              <details>
                                <summary>Consultar evidência</summary>
                                <p>{metadataField.evidence}</p>
                              </details>
                          )}

                          {hasSuggestion && (
                              <p className="field-confidence">
                                Confiança estimada:{" "}
                                {(metadataField.confidence * 100).toFixed(0)}%
                              </p>
                          )}

                          <label htmlFor={`field-${field.key}`}>
                            {field.list
                                ? "Editar valores (um por linha)"
                                : "Editar valor"}
                          </label>

                          {field.multiline ? (
                              <textarea
                                  id={`field-${field.key}`}
                                  rows={3}
                                  value={drafts[field.key] ?? ""}
                                  onChange={(event) =>
                                      setDrafts((previous) => ({
                                        ...previous,
                                        [field.key]: event.target.value,
                                      }))
                                  }
                                  placeholder="Introduz o valor..."
                              />
                          ) : (
                              <input
                                  id={`field-${field.key}`}
                                  type="text"
                                  value={drafts[field.key] ?? ""}
                                  onChange={(event) =>
                                      setDrafts((previous) => ({
                                        ...previous,
                                        [field.key]: event.target.value,
                                      }))
                                  }
                                  placeholder="Introduz o valor..."
                              />
                          )}

                          <div className="review-actions">
                            <button
                                type="button"
                                className="button-accept"
                                disabled={
                                    reviewLoading !== null ||
                                    !hasSuggestion ||
                                    isConfirmed
                                }
                                onClick={() => acceptSuggestion(field.key)}
                            >
                              Aceitar
                            </button>

                            <button
                                type="button"
                                className="button-edit"
                                disabled={reviewLoading !== null}
                                onClick={() => editAndConfirm(field)}
                            >
                              Confirmar edição
                            </button>

                            <button
                                type="button"
                                className="button-reject"
                                disabled={
                                    reviewLoading !== null ||
                                    metadataField.status === "rejected"
                                }
                                onClick={() => rejectSuggestion(field.key)}
                            >
                              Rejeitar
                            </button>
                          </div>

                          {reviewLoading === field.key && (
                              <p className="hint">A guardar revisão...</p>
                          )}

                          {field.required &&
                              !hasSuggestion &&
                              !hasValue(currentValue) && (
                                  <p className="field-warning">
                                    Este campo obrigatório precisa de um valor
                                    fornecido pelo utilizador.
                                  </p>
                              )}
                        </article>
                    );
                  })}
                </div>
              </section>

              {confirmation && (
                  <section className="panel">
                    <p className="eyebrow">REVIEW SUMMARY</p>
                    <h2>4. Estado da confirmação</h2>

                    <p>
                      {confirmation.can_generate_croissant
                          ? "Todos os campos obrigatórios estão confirmados."
                          : "Ainda existem campos obrigatórios por resolver."}
                    </p>

                    {confirmation.pending_fields.length > 0 && (
                        <>
                          <h3>Campos pendentes</h3>
                          <ul>
                            {confirmation.pending_fields.map((field) => (
                                <li key={field}>{field}</li>
                            ))}
                          </ul>
                        </>
                    )}

                    {confirmation.rejected_fields.length > 0 && (
                        <>
                          <h3>Campos rejeitados</h3>
                          <ul>
                            {confirmation.rejected_fields.map((field) => (
                                <li key={field}>{field}</li>
                            ))}
                          </ul>
                        </>
                    )}

                    {confirmation.can_generate_croissant && (
                        <div className="message success">
                          <strong>Revisão concluída.</strong>
                          <p>
                            Os metadados estão prontos para a próxima etapa:
                            geração do ficheiro Croissant.
                          </p>
                        </div>
                    )}

                    {!confirmation.can_generate_croissant && (
                        <p className="hint">
                          Para continuar, resolve os campos obrigatórios
                          indicados acima.
                        </p>
                    )}
                  </section>
              )}
            </>
        )}

        {repositoryResult?.warnings &&
            repositoryResult.warnings.length > 0 && (
                <section className="message warning">
                  <h2>Avisos da análise</h2>
                  <ul>
                    {repositoryResult.warnings.map((warning, index) => (
                        <li key={`${index}-${warning}`}>{warning}</li>
                    ))}
                  </ul>
                </section>
            )}
      </main>
  );
}

export default App;
