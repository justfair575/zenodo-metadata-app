
import { useState, type FormEvent } from "react";
import "./App.css";

type MetadataFile = {
  path: string;
  size?: number;
  status: string;
  content?: string;
};

type DatasetFile = {
  path: string;
  size: number;
  extension: string;
};

type Analysis = {
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
  };
  metadata_files: MetadataFile[];
  dataset_candidates: DatasetFile[];
  warnings: string[];
};

function App() {
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setAnalysis(null);

    try {
      const response = await fetch("http://localhost:8000/api/v1/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          ...(ref.trim() ? { ref: ref.trim() } : {}),
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
            typeof data.detail === "string"
                ? data.detail
                : "Não foi possível analisar o repositório.",
        );
      }

      setAnalysis(data as Analysis);
    } catch (err) {
      setError(
          err instanceof Error
              ? err.message
              : "Erro inesperado. Verifica se o backend está ativo.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
      <main className="page">
        <header className="hero">
          <p className="eyebrow">DATASET CURATION</p>
          <h1>Zenodo Metadata Assistant</h1>
          <p className="subtitle">
            Analisa um repositório GitHub e identifica ficheiros relevantes para
            melhorar os metadados do teu dataset.
          </p>
        </header>

        <section className="panel">
          <form onSubmit={analyze}>
            <label htmlFor="repo-url">URL do repositório GitHub</label>
            <input
                id="repo-url"
                type="url"
                placeholder="https://github.com/owner/repo"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
            />

            <label htmlFor="repo-ref">Branch, tag ou commit (opcional)</label>
            <input
                id="repo-ref"
                type="text"
                placeholder="Por omissão, usa a branch predefinida"
                value={ref}
                onChange={(event) => setRef(event.target.value)}
                maxLength={200}
            />

            <div className="form-footer">
              <p className="hint">Nesta versão, só são suportados repositórios públicos.</p>
              <button disabled={loading} type="submit">
                {loading ? "A analisar..." : "Analisar repositório"}
              </button>
            </div>
          </form>
        </section>

        {error && (
            <section className="message error" role="alert">
              <strong>Não foi possível analisar</strong>
              <p>{error}</p>
            </section>
        )}

        {analysis && (
            <>
              <section className="panel">
                <p className="eyebrow">REPOSITÓRIO ANALISADO</p>
                <h2>{analysis.repository.full_name}</h2>
                <p>{analysis.repository.description ?? "Sem descrição."}</p>
                <a href={analysis.repository.url} target="_blank" rel="noreferrer">
                  Abrir no GitHub ↗
                </a>

                <dl className="details">
                  <dt>Branch predefinida</dt>
                  <dd>{analysis.repository.default_branch}</dd>
                  <dt>Referência analisada</dt>
                  <dd>{analysis.repository.selected_ref}</dd>
                  <dt>Commit SHA</dt>
                  <dd className="hash">{analysis.repository.commit_sha}</dd>
                  <dt>Licença reportada</dt>
                  <dd>{analysis.repository.license ?? "Não identificada"}</dd>
                </dl>
              </section>

              <section className="stats">
                <article className="stat">
                  <strong>{analysis.inventory.total_files}</strong>
                  <span>Ficheiros na árvore</span>
                </article>
                <article className="stat">
                  <strong>{analysis.inventory.metadata_files_read}</strong>
                  <span>Ficheiros de metadados lidos</span>
                </article>
                <article className="stat">
                  <strong>{analysis.inventory.dataset_candidates_found}</strong>
                  <span>Possíveis ficheiros de dados</span>
                </article>
              </section>

              {analysis.warnings.length > 0 && (
                  <section className="message warning">
                    <h2>Avisos</h2>
                    <ul>
                      {analysis.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </section>
              )}

              <section className="panel">
                <h2>Ficheiros de metadados</h2>
                {analysis.metadata_files.length === 0 ? (
                    <p>Não foram encontrados ficheiros com nomes reconhecidos.</p>
                ) : (
                    <ul className="file-list">
                      {analysis.metadata_files.map((file) => (
                          <li key={file.path}>
                            <strong>{file.path}</strong>
                            <span className="file-status">{file.status}</span>
                            {file.content !== undefined && (
                                <details>
                                  <summary>Pré-visualizar conteúdo</summary>
                                  <pre>{file.content}</pre>
                                </details>
                            )}
                          </li>
                      ))}
                    </ul>
                )}
              </section>

              <section className="panel">
                <h2>Possíveis ficheiros de dados</h2>
                <p className="hint">
                  A deteção baseia-se na extensão; não confirma que o ficheiro seja
                  um dataset utilizável.
                </p>
                {analysis.dataset_candidates.length === 0 ? (
                    <p>Não foram encontrados ficheiros com extensões suportadas.</p>
                ) : (
                    <ul className="file-list">
                      {analysis.dataset_candidates.map((file) => (
                          <li key={file.path}>
                            <strong>{file.path}</strong>
                            <span className="file-status">
                      {file.extension || "Sem extensão"} ·{" "}
                              {file.size.toLocaleString()} bytes
                    </span>
                          </li>
                      ))}
                    </ul>
                )}
              </section>
            </>
        )}
      </main>
  );
}

export default App;
