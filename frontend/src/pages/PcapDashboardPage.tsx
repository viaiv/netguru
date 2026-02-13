/**
 * PcapDashboardPage — fullscreen dashboard com graficos Recharts
 * para dados estruturados de analise PCAP.
 *
 * Aberta em nova aba via /pcap/:messageId
 */
import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  AreaChart, Area,
} from 'recharts';
import { fetchPcapData, getErrorMessage } from '../services/api';
import type { IPcapAnalysisData } from '../types/pcapAnalysis';

const COLORS = [
  '#81d742', '#1665cf', '#e6a817', '#af0000', '#4ec9b0',
  '#c586c0', '#9cdcfe', '#dcdcaa', '#d24444', '#6a9955',
  '#a8e06c', '#78a6e6',
];

type TTab = 'overview' | 'traffic' | 'security' | 'wireless';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatBps(bps: number): string {
  if (bps < 1000) return `${bps.toFixed(0)} bps`;
  if (bps < 1_000_000) return `${(bps / 1000).toFixed(1)} Kbps`;
  return `${(bps / 1_000_000).toFixed(2)} Mbps`;
}

function PcapDashboardPage() {
  const { messageId } = useParams<{ messageId: string }>();
  const [data, setData] = useState<IPcapAnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TTab>('overview');

  useEffect(() => {
    if (!messageId) return;
    setLoading(true);
    setError(null);
    fetchPcapData(messageId)
      .then((raw) => setData(raw as unknown as IPcapAnalysisData))
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [messageId]);

  if (loading) {
    return (
      <div className="pcap-dashboard">
        <p className="pcap-dashboard__loading">Carregando dados PCAP...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="pcap-dashboard">
        <div className="pcap-dashboard__error">
          <p>{error || 'Dados nao encontrados.'}</p>
          <Link to="/chat" className="btn btn-primary">Voltar ao Chat</Link>
        </div>
      </div>
    );
  }

  const tabs: { key: TTab; label: string; show: boolean }[] = [
    { key: 'overview', label: 'Visao Geral', show: true },
    { key: 'traffic', label: 'Trafego', show: true },
    { key: 'security', label: 'Seguranca', show: !!(data.http || data.tls || data.voip) },
    { key: 'wireless', label: 'Wireless', show: !!data.is_wireless },
  ];

  return (
    <div className="pcap-dashboard">
      <header className="pcap-dashboard__header">
        <div>
          <h1 className="pcap-dashboard__title">PCAP Dashboard</h1>
          <p className="pcap-dashboard__subtitle">
            {data.total_packets?.toLocaleString()} pacotes
            {data.capture_duration ? ` | ${data.capture_duration.toFixed(1)}s` : ''}
            {data.is_wireless ? ' | Wi-Fi (802.11)' : ' | Ethernet/IP'}
          </p>
        </div>
        <Link to="/chat" className="ghost-btn">Voltar ao Chat</Link>
      </header>

      {/* Tabs */}
      <nav className="pcap-tabs">
        {tabs.filter((t) => t.show).map((t) => (
          <button
            key={t.key}
            type="button"
            className={`pcap-tabs__item ${tab === t.key ? 'pcap-tabs__item--active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <div className="pcap-dashboard__content">
        {tab === 'overview' && <OverviewTab data={data} />}
        {tab === 'traffic' && <TrafficTab data={data} />}
        {tab === 'security' && <SecurityTab data={data} />}
        {tab === 'wireless' && data.wireless && <WirelessTab data={data} />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Overview Tab                                                       */
/* ------------------------------------------------------------------ */

function OverviewTab({ data }: { data: IPcapAnalysisData }) {
  return (
    <>
      {/* Stats header */}
      <div className="pcap-stats-grid">
        <div className="pcap-stat-card">
          <p className="pcap-stat-card__label">Pacotes</p>
          <p className="pcap-stat-card__value">{data.total_packets?.toLocaleString()}</p>
        </div>
        <div className="pcap-stat-card">
          <p className="pcap-stat-card__label">Duracao</p>
          <p className="pcap-stat-card__value">{data.capture_duration?.toFixed(1)}s</p>
        </div>
        {data.bandwidth && (
          <>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Total Bytes</p>
              <p className="pcap-stat-card__value">{formatBytes(data.bandwidth.total_bytes)}</p>
            </div>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Avg Throughput</p>
              <p className="pcap-stat-card__value">{formatBps(data.bandwidth.avg_bps)}</p>
            </div>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Peak Throughput</p>
              <p className="pcap-stat-card__value">{formatBps(data.bandwidth.peak_bps)}</p>
            </div>
          </>
        )}
        {data.tcp_issues && (
          <div className="pcap-stat-card">
            <p className="pcap-stat-card__label">TCP Retrans</p>
            <p className="pcap-stat-card__value">{data.tcp_issues.retransmissions}</p>
          </div>
        )}
      </div>

      {/* Charts row */}
      <div className="pcap-charts-row">
        {/* Protocol Pie */}
        {data.protocols && data.protocols.length > 0 && (
          <div className="pcap-card">
            <h3 className="pcap-card__title">Distribuicao de Protocolos</h3>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={data.protocols}
                  dataKey="count"
                  nameKey="protocol"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name, percent }: { name?: string; percent?: number }) => `${name ?? ''} (${((percent ?? 0) * 100).toFixed(1)}%)`}
                >
                  {data.protocols.map((_entry, idx) => (
                    <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Top Talkers Bar */}
        {data.top_talkers && data.top_talkers.length > 0 && (
          <div className="pcap-card">
            <h3 className="pcap-card__title">Top Talkers</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.top_talkers.slice(0, 10)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(31,31,31,0.1)" />
                <XAxis type="number" />
                <YAxis dataKey="ip" type="category" width={120} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value: unknown) => formatBytes(value as number)} />
                <Bar dataKey="bytes" fill="#1665cf" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Anomalies table */}
      {data.anomalies && data.anomalies.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Anomalias Detectadas</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr>
                  <th>Severidade</th>
                  <th>Tipo</th>
                  <th>Descricao</th>
                </tr>
              </thead>
              <tbody>
                {data.anomalies.map((a, i) => (
                  <tr key={i}>
                    <td>
                      <span className={`pcap-anomaly-badge pcap-anomaly-badge--${a.severity}`}>
                        {a.severity}
                      </span>
                    </td>
                    <td>{a.type}</td>
                    <td>{a.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Traffic Tab                                                        */
/* ------------------------------------------------------------------ */

function TrafficTab({ data }: { data: IPcapAnalysisData }) {
  return (
    <>
      {/* Timeline area chart */}
      {data.time_buckets && data.time_buckets.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Timeline de Trafego</h3>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={data.time_buckets}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(31,31,31,0.1)" />
              <XAxis
                dataKey="timestamp"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: string) => {
                  const d = new Date(v);
                  return `${d.getMinutes()}:${String(d.getSeconds()).padStart(2, '0')}`;
                }}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                labelFormatter={(v: unknown) => new Date(v as string).toLocaleTimeString()}
                formatter={(value: unknown, name: unknown) =>
                  name === 'bytes' ? formatBytes(value as number) : (value as number)
                }
              />
              <Area
                type="monotone"
                dataKey="packets"
                stroke="#81d742"
                fill="rgba(129,215,66,0.2)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Frame sizes bar */}
      {data.frame_sizes && data.frame_sizes.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Distribuicao de Frame Sizes</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.frame_sizes}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(31,31,31,0.1)" />
              <XAxis dataKey="range" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#4ec9b0" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Conversations table */}
      {data.conversations && data.conversations.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Top Conversations</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr>
                  <th>Origem</th>
                  <th>Destino</th>
                  <th>Protocolo</th>
                  <th>Pacotes</th>
                  <th>Bytes</th>
                </tr>
              </thead>
              <tbody>
                {data.conversations.slice(0, 20).map((c, i) => (
                  <tr key={i}>
                    <td className="pcap-table__mono">{c.src}</td>
                    <td className="pcap-table__mono">{c.dst}</td>
                    <td>{c.protocol}</td>
                    <td>{c.packets}</td>
                    <td>{formatBytes(c.bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* DNS queries */}
      {data.dns_queries && data.dns_queries.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">DNS Queries</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr>
                  <th>Query</th>
                  <th>Tipo</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                {data.dns_queries.slice(0, 20).map((d, i) => (
                  <tr key={i}>
                    <td className="pcap-table__mono">{d.query}</td>
                    <td>{d.type}</td>
                    <td>{d.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Security Tab                                                       */
/* ------------------------------------------------------------------ */

function SecurityTab({ data }: { data: IPcapAnalysisData }) {
  return (
    <>
      {/* HTTP */}
      {data.http && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">HTTP Analysis</h3>
          <div className="pcap-security-grid">
            {data.http.methods && Object.keys(data.http.methods).length > 0 && (
              <div>
                <h4 className="pcap-card__subtitle">Methods</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Method</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.http.methods).map(([m, c]) => (
                        <tr key={m}><td>{m}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {data.http.status_codes && Object.keys(data.http.status_codes).length > 0 && (
              <div>
                <h4 className="pcap-card__subtitle">Status Codes</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Code</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.http.status_codes).map(([s, c]) => (
                        <tr key={s}><td>{s}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          {data.http.top_urls && data.http.top_urls.length > 0 && (
            <>
              <h4 className="pcap-card__subtitle">Top URLs</h4>
              <div className="pcap-table-wrapper">
                <table className="pcap-table pcap-table--compact">
                  <thead><tr><th>URL</th><th>Count</th></tr></thead>
                  <tbody>
                    {data.http.top_urls.slice(0, 15).map((u, i) => (
                      <tr key={i}><td className="pcap-table__mono">{u.url}</td><td>{u.count}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {data.http.top_hosts && data.http.top_hosts.length > 0 && (
            <>
              <h4 className="pcap-card__subtitle">Top Hosts</h4>
              <div className="pcap-table-wrapper">
                <table className="pcap-table pcap-table--compact">
                  <thead><tr><th>Host</th><th>Count</th></tr></thead>
                  <tbody>
                    {data.http.top_hosts.slice(0, 15).map((h, i) => (
                      <tr key={i}><td className="pcap-table__mono">{h.host}</td><td>{h.count}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* TLS */}
      {data.tls && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">TLS/SSL Analysis</h3>
          <div className="pcap-security-grid">
            {data.tls.versions && Object.keys(data.tls.versions).length > 0 && (
              <div>
                <h4 className="pcap-card__subtitle">TLS Versions</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Version</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.tls.versions).map(([v, c]) => (
                        <tr key={v}><td>{v}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {data.tls.sni_hosts && data.tls.sni_hosts.length > 0 && (
              <div>
                <h4 className="pcap-card__subtitle">SNI Hosts</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Host</th><th>Count</th></tr></thead>
                    <tbody>
                      {data.tls.sni_hosts.slice(0, 15).map((h, i) => (
                        <tr key={i}><td className="pcap-table__mono">{h.host}</td><td>{h.count}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          {data.tls.cipher_suites && data.tls.cipher_suites.length > 0 && (
            <>
              <h4 className="pcap-card__subtitle">Cipher Suites</h4>
              <div className="pcap-table-wrapper">
                <table className="pcap-table pcap-table--compact">
                  <thead><tr><th>Cipher</th><th>Count</th></tr></thead>
                  <tbody>
                    {data.tls.cipher_suites.slice(0, 15).map((c, i) => (
                      <tr key={i}><td className="pcap-table__mono">{c.cipher}</td><td>{c.count}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* VoIP */}
      {data.voip && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">VoIP / SIP Analysis</h3>
          <div className="pcap-security-grid">
            {data.voip.sip_methods && Object.keys(data.voip.sip_methods).length > 0 && (
              <div>
                <h4 className="pcap-card__subtitle">SIP Methods</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Method</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.voip.sip_methods).map(([m, c]) => (
                        <tr key={m}><td>{m}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {data.voip.sip_responses && Object.keys(data.voip.sip_responses).length > 0 && (
              <div>
                <h4 className="pcap-card__subtitle">SIP Responses</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Response</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.voip.sip_responses).map(([r, c]) => (
                        <tr key={r}><td>{r}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          <p className="pcap-card__detail">
            RTP Streams: {data.voip.rtp_streams}
            {data.voip.rtp_codecs?.length > 0 && ` | Codecs: ${data.voip.rtp_codecs.join(', ')}`}
          </p>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Wireless Tab                                                       */
/* ------------------------------------------------------------------ */

function WirelessTab({ data }: { data: IPcapAnalysisData }) {
  const w = data.wireless!;

  const frameTypeData = w.frame_types ? [
    { name: 'Management', value: w.frame_types.management },
    { name: 'Control', value: w.frame_types.control },
    { name: 'Data', value: w.frame_types.data },
  ] : [];

  const channelData = w.channels
    ? Object.entries(w.channels).map(([ch, count]) => ({ channel: `Ch ${ch}`, count }))
    : [];

  return (
    <>
      {/* Wireless stats */}
      <div className="pcap-stats-grid">
        {w.signal_stats && (
          <>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Signal Avg</p>
              <p className="pcap-stat-card__value">{w.signal_stats.avg_dbm} dBm</p>
            </div>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Signal Min</p>
              <p className="pcap-stat-card__value">{w.signal_stats.min_dbm} dBm</p>
            </div>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Signal Max</p>
              <p className="pcap-stat-card__value">{w.signal_stats.max_dbm} dBm</p>
            </div>
          </>
        )}
        <div className="pcap-stat-card">
          <p className="pcap-stat-card__label">Retry Rate</p>
          <p className="pcap-stat-card__value">{(w.retry_rate * 100).toFixed(1)}%</p>
        </div>
      </div>

      <div className="pcap-charts-row">
        {/* Frame types pie */}
        {frameTypeData.length > 0 && (
          <div className="pcap-card">
            <h3 className="pcap-card__title">Frame Types</h3>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={frameTypeData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={({ name, value }) => `${name}: ${value}`}
                >
                  {frameTypeData.map((_e, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Channels bar */}
        {channelData.length > 0 && (
          <div className="pcap-card">
            <h3 className="pcap-card__title">Channels</h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={channelData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(31,31,31,0.1)" />
                <XAxis dataKey="channel" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#e6a817" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* SSIDs */}
      {w.ssids && w.ssids.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">SSIDs Detectados</h3>
          <div className="pcap-ssid-list">
            {w.ssids.map((ssid, i) => (
              <span key={i} className="pcap-ssid-chip">{ssid}</span>
            ))}
          </div>
        </div>
      )}

      {/* Deauth events */}
      {w.deauth_events && w.deauth_events.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Deauth/Disassoc Events</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Destination</th>
                  <th>Reason Code</th>
                  <th>Reason</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                {w.deauth_events.map((e, i) => (
                  <tr key={i}>
                    <td className="pcap-table__mono">{e.src}</td>
                    <td className="pcap-table__mono">{e.dst}</td>
                    <td>{e.reason_code}</td>
                    <td>{e.reason_text}</td>
                    <td>{e.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

export default PcapDashboardPage;
