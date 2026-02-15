/**
 * EvidencePanel — mostra evidencias e confianca por mensagem do assistente.
 */
import { useMemo, useState } from 'react';

interface EvidencePanelProps {
  metadata: Record<string, unknown> | null;
}

interface EvidenceItem {
  id: string;
  type: string;
  source: string;
  status: string;
  strength: 'strong' | 'medium' | 'weak';
  summary: string;
  details: Record<string, unknown> | null;
}

interface EvidencePayload {
  items: EvidenceItem[];
  totalCount: number;
  strongCount: number;
  mediumCount: number;
  weakCount: number;
  failedCount: number;
}

interface ConfidencePayload {
  score: number;
  level: 'high' | 'medium' | 'low';
  reasons: string[];
  warning: string | null;
}

interface Citation {
  index: number;
  source_type: string;
  excerpt: string;
  similarity: number;
  document_id?: string;
  document_name?: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

function parseEvidence(metadata: Record<string, unknown> | null): EvidencePayload | null {
  if (!metadata) {
    return null;
  }
  const evidenceRaw = asRecord(metadata.evidence);
  if (!evidenceRaw) {
    return null;
  }

  const itemsRaw = Array.isArray(evidenceRaw.items) ? evidenceRaw.items : [];
  const items: EvidenceItem[] = itemsRaw
    .map((candidate, index) => {
      const item = asRecord(candidate);
      if (!item) return null;
      const strengthRaw = String(item.strength ?? 'weak');
      const strength: EvidenceItem['strength'] =
        strengthRaw === 'strong' || strengthRaw === 'medium' ? strengthRaw : 'weak';
      return {
        id: String(item.id ?? `item-${index}`),
        type: String(item.type ?? 'unknown'),
        source: String(item.source ?? 'unknown'),
        status: String(item.status ?? 'unknown'),
        strength,
        summary: String(item.summary ?? ''),
        details: asRecord(item.details),
      };
    })
    .filter((item): item is EvidenceItem => item !== null);

  return {
    items,
    totalCount: asNumber(evidenceRaw.total_count, items.length),
    strongCount: asNumber(evidenceRaw.strong_count),
    mediumCount: asNumber(evidenceRaw.medium_count),
    weakCount: asNumber(evidenceRaw.weak_count),
    failedCount: asNumber(evidenceRaw.failed_count),
  };
}

function parseConfidence(metadata: Record<string, unknown> | null): ConfidencePayload | null {
  if (!metadata) {
    return null;
  }
  const confidenceRaw = asRecord(metadata.confidence);
  if (!confidenceRaw) {
    return null;
  }
  const levelRaw = String(confidenceRaw.level ?? 'low');
  const level: ConfidencePayload['level'] =
    levelRaw === 'high' || levelRaw === 'medium' ? levelRaw : 'low';
  return {
    score: asNumber(confidenceRaw.score),
    level,
    reasons: asStringList(confidenceRaw.reasons),
    warning: typeof confidenceRaw.warning === 'string' ? confidenceRaw.warning : null,
  };
}

function confidenceLabel(level: ConfidencePayload['level']): string {
  if (level === 'high') return 'alta';
  if (level === 'medium') return 'media';
  return 'baixa';
}

function detailValue(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function prettyKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function parseCitations(metadata: Record<string, unknown> | null): Citation[] {
  if (!metadata) return [];
  const raw = metadata.citations;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((c): c is Record<string, unknown> => typeof c === 'object' && c !== null)
    .map((c) => ({
      index: asNumber(c.index, 0),
      source_type: String(c.source_type ?? 'unknown'),
      excerpt: String(c.excerpt ?? ''),
      similarity: asNumber(c.similarity, 0),
      document_id: typeof c.document_id === 'string' ? c.document_id : undefined,
      document_name: typeof c.document_name === 'string' ? c.document_name : undefined,
    }));
}

function sourceLabel(sourceType: string): string {
  if (sourceType === 'rag_global') return 'Docs de vendors';
  if (sourceType === 'rag_local') return 'Seus documentos';
  return sourceType;
}

function EvidencePanel({ metadata }: EvidencePanelProps) {
  const evidence = useMemo(() => parseEvidence(metadata), [metadata]);
  const confidence = useMemo(() => parseConfidence(metadata), [metadata]);
  const citations = useMemo(() => parseCitations(metadata), [metadata]);
  const [expanded, setExpanded] = useState(false);
  const [citationsExpanded, setCitationsExpanded] = useState(false);

  if (!evidence && !confidence && citations.length === 0) {
    return null;
  }

  const items = evidence?.items ?? [];
  const canExpand = items.length > 0;

  return (
    <div className="evidence-panel">
      <div className="evidence-panel__header">
        <span className="evidence-panel__title">Evidencias</span>
        {confidence && (
          <span className={`confidence-badge confidence-badge--${confidence.level}`}>
            Confianca {confidenceLabel(confidence.level)} · {Math.round(confidence.score)}/100
          </span>
        )}
      </div>

      {evidence && (
        <p className="evidence-panel__summary">
          {evidence.strongCount} fortes · {evidence.mediumCount} medias · {evidence.weakCount} fracas
          {evidence.failedCount > 0 ? ` · ${evidence.failedCount} falhas` : ''}
        </p>
      )}

      {confidence?.reasons.length ? (
        <p className="evidence-panel__reasons">{confidence.reasons.join(' ')}</p>
      ) : null}

      {confidence?.warning && (
        <p className="evidence-panel__warning">{confidence.warning}</p>
      )}

      {canExpand ? (
        <>
          <button
            type="button"
            className="evidence-panel__toggle"
            onClick={() => setExpanded((prev) => !prev)}
          >
            {expanded ? 'Ocultar evidencias' : `Ver evidencias (${evidence?.totalCount ?? items.length})`}
          </button>

          {expanded && (
            <div className="evidence-panel__list">
              {items.map((item) => {
                const details = item.details ? Object.entries(item.details) : [];
                return (
                  <div
                    key={item.id}
                    className={`evidence-item evidence-item--${item.strength}`}
                  >
                    <div className="evidence-item__meta">
                      <span className="evidence-item__source">{item.source}</span>
                      <span className="evidence-item__status">{item.status}</span>
                    </div>
                    <p className="evidence-item__summary">{item.summary}</p>

                    {details.length > 0 && (
                      <div className="evidence-item__details">
                        {details.map(([key, value]) => (
                          <div key={`${item.id}-${key}`} className="evidence-item__detail-row">
                            <p className="evidence-item__detail-key">{prettyKey(key)}</p>
                            <pre className="evidence-item__detail-pre">{detailValue(value)}</pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      ) : null}

      {citations.length > 0 && (
        <>
          <button
            type="button"
            className="evidence-panel__toggle"
            onClick={() => setCitationsExpanded((prev) => !prev)}
          >
            {citationsExpanded ? 'Ocultar fontes' : `Fontes (${citations.length})`}
          </button>

          {citationsExpanded && (
            <div className="evidence-panel__citations">
              {citations.map((c) => (
                <div key={`cite-${c.index}`} className="citation-item">
                  <div className="citation-item__meta">
                    <span className="citation-item__index">[{c.index}]</span>
                    <span className="citation-item__source">{sourceLabel(c.source_type)}</span>
                    {c.document_name && (
                      <span className="citation-item__doc">{c.document_name}</span>
                    )}
                    <span className="citation-item__sim">{Math.round(c.similarity * 100)}%</span>
                  </div>
                  <p className="citation-item__excerpt">{c.excerpt}</p>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {citations.length === 0 && confidence && confidence.level === 'low' && (
        <p className="evidence-panel__no-citations">
          Sem fontes documentais — resposta baseada em conhecimento geral do modelo.
        </p>
      )}
    </div>
  );
}

export default EvidencePanel;
