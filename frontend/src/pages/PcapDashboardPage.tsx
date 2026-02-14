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

function hasData(obj: Record<string, unknown> | unknown[] | undefined | null): boolean {
  if (!obj) return false;
  if (Array.isArray(obj)) return obj.length > 0;
  return Object.keys(obj).length > 0;
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

  const hasHttp = hasData(data.http_methods) || hasData(data.http_status_codes);
  const hasTls = hasData(data.tls_versions) || (data.tls_sni_hosts?.length > 0);
  const hasVoip = hasData(data.voip_sip_methods) || data.voip_rtp_streams > 0;
  const hasSecurity = hasHttp || hasTls || hasVoip;

  const tabs: { key: TTab; label: string; show: boolean }[] = [
    { key: 'overview', label: 'Visao Geral', show: true },
    { key: 'traffic', label: 'Trafego', show: true },
    { key: 'security', label: 'Seguranca', show: hasSecurity },
    { key: 'wireless', label: 'Wireless', show: !!data.is_wireless },
  ];

  return (
    <div className="pcap-dashboard">
      <header className="pcap-dashboard__header">
        <div>
          <h1 className="pcap-dashboard__title">PCAP Dashboard</h1>
          <p className="pcap-dashboard__subtitle">
            {data.total_packets?.toLocaleString()} pacotes
            {data.duration_seconds ? ` | ${data.duration_seconds.toFixed(1)}s` : ''}
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
        {tab === 'wireless' && data.is_wireless && <WirelessTab data={data} />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Overview Tab                                                       */
/* ------------------------------------------------------------------ */

function OverviewTab({ data }: { data: IPcapAnalysisData }) {
  // Convert protocols dict to array for PieChart
  const protocolEntries = Object.entries(data.protocols || {})
    .map(([protocol, count]) => ({ protocol, count }))
    .sort((a, b) => b.count - a.count);

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
          <p className="pcap-stat-card__value">{data.duration_seconds?.toFixed(1)}s</p>
        </div>
        <div className="pcap-stat-card">
          <p className="pcap-stat-card__label">Total Bytes</p>
          <p className="pcap-stat-card__value">{formatBytes(data.total_bytes || 0)}</p>
        </div>
        <div className="pcap-stat-card">
          <p className="pcap-stat-card__label">Avg Throughput</p>
          <p className="pcap-stat-card__value">{formatBps(data.avg_throughput_bps || 0)}</p>
        </div>
        <div className="pcap-stat-card">
          <p className="pcap-stat-card__label">Peak Throughput</p>
          <p className="pcap-stat-card__value">{formatBps(data.peak_throughput_bps || 0)}</p>
        </div>
        {data.tcp_issues && data.tcp_issues.length > 0 && (
          <div className="pcap-stat-card">
            <p className="pcap-stat-card__label">TCP Issues</p>
            <p className="pcap-stat-card__value">{data.tcp_issues.length}</p>
          </div>
        )}
      </div>

      {/* Charts row */}
      <div className="pcap-charts-row">
        {/* Protocol Pie */}
        {protocolEntries.length > 0 && (
          <div className="pcap-card">
            <h3 className="pcap-card__title">Distribuicao de Protocolos</h3>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={protocolEntries}
                  dataKey="count"
                  nameKey="protocol"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name, percent }: { name?: string; percent?: number }) =>
                    `${name ?? ''} (${((percent ?? 0) * 100).toFixed(1)}%)`
                  }
                >
                  {protocolEntries.map((_entry, idx) => (
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
                <YAxis dataKey="ip" type="category" width={140} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value: unknown) => formatBytes(value as number)} />
                <Bar dataKey="bytes" fill="#1665cf" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Network protocols detected */}
      {data.network_protocols && data.network_protocols.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Protocolos de Rede Detectados</h3>
          <div className="pcap-ssid-list">
            {data.network_protocols.map((p, i) => (
              <span key={i} className="pcap-ssid-chip">{p}</span>
            ))}
          </div>
        </div>
      )}

      {/* Anomalies */}
      {data.anomalies && data.anomalies.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Anomalias Detectadas</h3>
          <ul className="pcap-anomaly-list">
            {data.anomalies.map((a, i) => (
              <li key={i} className="pcap-anomaly-item">{a}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Traffic Tab                                                        */
/* ------------------------------------------------------------------ */

function TrafficTab({ data }: { data: IPcapAnalysisData }) {
  // Convert frame_size_distribution dict to sorted array
  const frameSizeOrder = ['0-64', '65-128', '129-256', '257-512', '513-1024', '1025-1518', '1519-9000 (Jumbo)', '9001+'];
  const frameSizes = Object.entries(data.frame_size_distribution || {})
    .map(([range, count]) => ({ range, count }))
    .sort((a, b) => {
      const ia = frameSizeOrder.indexOf(a.range);
      const ib = frameSizeOrder.indexOf(b.range);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

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
                dataKey="time_offset"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => `${v.toFixed(0)}s`}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                labelFormatter={(v: unknown) => `${Number(v).toFixed(1)}s`}
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
                name="Pacotes"
              />
              <Area
                type="monotone"
                dataKey="bytes"
                stroke="#1665cf"
                fill="rgba(22,101,207,0.1)"
                strokeWidth={1}
                name="bytes"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Frame sizes bar */}
      {frameSizes.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Distribuicao de Frame Sizes</h3>
          {data.frame_size_stats && (
            <p className="pcap-card__detail" style={{ marginTop: 0, marginBottom: 12 }}>
              Min: {data.frame_size_stats.min}B | Max: {data.frame_size_stats.max}B |
              Avg: {data.frame_size_stats.avg?.toFixed(1)}B | Mediana: {data.frame_size_stats.median}B
            </p>
          )}
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={frameSizes}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(31,31,31,0.1)" />
              <XAxis dataKey="range" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#4ec9b0" radius={[4, 4, 0, 0]} name="Pacotes" />
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
                  <th>Pacotes</th>
                  <th>Bytes</th>
                </tr>
              </thead>
              <tbody>
                {data.conversations.slice(0, 20).map((c, i) => (
                  <tr key={i}>
                    <td className="pcap-table__mono">{c.src}</td>
                    <td className="pcap-table__mono">{c.dst}</td>
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
                <tr><th>Query</th></tr>
              </thead>
              <tbody>
                {data.dns_queries.slice(0, 30).map((q, i) => (
                  <tr key={i}><td className="pcap-table__mono">{q}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TCP Issues */}
      {data.tcp_issues && data.tcp_issues.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">TCP Issues</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Origem</th>
                  <th>Destino</th>
                </tr>
              </thead>
              <tbody>
                {data.tcp_issues.slice(0, 20).map((t, i) => (
                  <tr key={i}>
                    <td>{t.type}</td>
                    <td className="pcap-table__mono">{t.src}</td>
                    <td className="pcap-table__mono">{t.dst}</td>
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
  const hasHttp = hasData(data.http_methods) || hasData(data.http_status_codes);
  const hasTls = hasData(data.tls_versions) || (data.tls_sni_hosts?.length > 0);
  const hasVoip = hasData(data.voip_sip_methods) || data.voip_rtp_streams > 0;

  return (
    <>
      {/* HTTP */}
      {hasHttp && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">HTTP Analysis</h3>
          <div className="pcap-security-grid">
            {hasData(data.http_methods) && (
              <div>
                <h4 className="pcap-card__subtitle">Methods</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Method</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.http_methods).map(([m, c]) => (
                        <tr key={m}><td>{m}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {hasData(data.http_status_codes) && (
              <div>
                <h4 className="pcap-card__subtitle">Status Codes</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Code</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.http_status_codes).map(([s, c]) => (
                        <tr key={s}><td>{s}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          {data.http_urls && data.http_urls.length > 0 && (
            <>
              <h4 className="pcap-card__subtitle">URLs</h4>
              <div className="pcap-table-wrapper">
                <table className="pcap-table pcap-table--compact">
                  <thead><tr><th>URL</th></tr></thead>
                  <tbody>
                    {data.http_urls.slice(0, 20).map((u, i) => (
                      <tr key={i}><td className="pcap-table__mono">{u}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {data.http_hosts && data.http_hosts.length > 0 && (
            <>
              <h4 className="pcap-card__subtitle">Hosts</h4>
              <div className="pcap-table-wrapper">
                <table className="pcap-table pcap-table--compact">
                  <thead><tr><th>Host</th></tr></thead>
                  <tbody>
                    {data.http_hosts.slice(0, 20).map((h, i) => (
                      <tr key={i}><td className="pcap-table__mono">{h}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* TLS */}
      {hasTls && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">TLS/SSL Analysis</h3>
          <div className="pcap-security-grid">
            {hasData(data.tls_versions) && (
              <div>
                <h4 className="pcap-card__subtitle">TLS Versions</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Version</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.tls_versions).map(([v, c]) => (
                        <tr key={v}><td>{v}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {data.tls_sni_hosts && data.tls_sni_hosts.length > 0 && (
              <div>
                <h4 className="pcap-card__subtitle">SNI Hosts</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Host</th></tr></thead>
                    <tbody>
                      {data.tls_sni_hosts.slice(0, 20).map((h, i) => (
                        <tr key={i}><td className="pcap-table__mono">{h}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          {data.tls_cipher_suites && data.tls_cipher_suites.length > 0 && (
            <>
              <h4 className="pcap-card__subtitle">Cipher Suites</h4>
              <div className="pcap-table-wrapper">
                <table className="pcap-table pcap-table--compact">
                  <thead><tr><th>Cipher</th></tr></thead>
                  <tbody>
                    {data.tls_cipher_suites.slice(0, 15).map((c, i) => (
                      <tr key={i}><td className="pcap-table__mono">{c}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* VoIP */}
      {hasVoip && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">VoIP / SIP Analysis</h3>
          <div className="pcap-security-grid">
            {hasData(data.voip_sip_methods) && (
              <div>
                <h4 className="pcap-card__subtitle">SIP Methods</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Method</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.voip_sip_methods).map(([m, c]) => (
                        <tr key={m}><td>{m}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {hasData(data.voip_sip_responses) && (
              <div>
                <h4 className="pcap-card__subtitle">SIP Responses</h4>
                <div className="pcap-table-wrapper">
                  <table className="pcap-table pcap-table--compact">
                    <thead><tr><th>Response</th><th>Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.voip_sip_responses).map(([r, c]) => (
                        <tr key={r}><td>{r}</td><td>{c}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          <p className="pcap-card__detail">
            RTP Streams: {data.voip_rtp_streams}
            {data.voip_rtp_codecs?.length > 0 && ` | Codecs: ${data.voip_rtp_codecs.join(', ')}`}
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
  // Convert wireless_frame_types dict to array for PieChart
  const frameTypeData = Object.entries(data.wireless_frame_types || {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  const channelData = Object.entries(data.channels || {})
    .map(([ch, count]) => ({ channel: `Ch ${ch}`, count }))
    .sort((a, b) => b.count - a.count);

  const retryRate = data.retry_stats?.rate_pct ?? 0;

  return (
    <>
      {/* Wireless stats */}
      <div className="pcap-stats-grid">
        {data.signal_stats && (
          <>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Signal Avg</p>
              <p className="pcap-stat-card__value">{data.signal_stats.avg_dBm?.toFixed(1)} dBm</p>
            </div>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Signal Min</p>
              <p className="pcap-stat-card__value">{data.signal_stats.min_dBm} dBm</p>
            </div>
            <div className="pcap-stat-card">
              <p className="pcap-stat-card__label">Signal Max</p>
              <p className="pcap-stat-card__value">{data.signal_stats.max_dBm} dBm</p>
            </div>
          </>
        )}
        <div className="pcap-stat-card">
          <p className="pcap-stat-card__label">Retry Rate</p>
          <p className="pcap-stat-card__value">{retryRate.toFixed(1)}%</p>
        </div>
        {data.signal_stats?.samples != null && (
          <div className="pcap-stat-card">
            <p className="pcap-stat-card__label">Samples</p>
            <p className="pcap-stat-card__value">{data.signal_stats.samples.toLocaleString()}</p>
          </div>
        )}
      </div>

      <div className="pcap-charts-row">
        {/* Frame types pie */}
        {frameTypeData.length > 0 && (
          <div className="pcap-card">
            <h3 className="pcap-card__title">Frame Types (802.11)</h3>
            <ResponsiveContainer width="100%" height={320}>
              <PieChart>
                <Pie
                  data={frameTypeData.slice(0, 10)}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name, percent }: { name?: string; percent?: number }) =>
                    `${name ?? ''} (${((percent ?? 0) * 100).toFixed(1)}%)`
                  }
                >
                  {frameTypeData.slice(0, 10).map((_e, i) => (
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
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={channelData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(31,31,31,0.1)" />
                <XAxis dataKey="channel" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#e6a817" radius={[4, 4, 0, 0]} name="Pacotes" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* SSIDs */}
      {data.ssids && data.ssids.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">SSIDs Detectados</h3>
          <div className="pcap-ssid-list">
            {data.ssids.map((ssid, i) => (
              <span key={i} className="pcap-ssid-chip">{ssid || '(hidden)'}</span>
            ))}
          </div>
        </div>
      )}

      {/* Frame types table (full) */}
      {frameTypeData.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Todos os Frame Types</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr><th>Tipo</th><th>Count</th><th>%</th></tr>
              </thead>
              <tbody>
                {frameTypeData.map((f) => (
                  <tr key={f.name}>
                    <td>{f.name}</td>
                    <td>{f.value.toLocaleString()}</td>
                    <td>{((f.value / data.total_packets) * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Deauth events */}
      {data.deauth_events && data.deauth_events.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Deauth Events</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Destination</th>
                  <th>Reason</th>
                  <th>Time (s)</th>
                </tr>
              </thead>
              <tbody>
                {data.deauth_events.map((e, i) => (
                  <tr key={i}>
                    <td className="pcap-table__mono">{e.src}</td>
                    <td className="pcap-table__mono">{e.dst}</td>
                    <td>{e.reason_text} ({e.reason})</td>
                    <td>{e.timestamp?.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Disassoc events */}
      {data.disassoc_events && data.disassoc_events.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Disassoc Events</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Destination</th>
                  <th>Reason</th>
                  <th>Time (s)</th>
                </tr>
              </thead>
              <tbody>
                {data.disassoc_events.map((e, i) => (
                  <tr key={i}>
                    <td className="pcap-table__mono">{e.src}</td>
                    <td className="pcap-table__mono">{e.dst}</td>
                    <td>{e.reason_text} ({e.reason})</td>
                    <td>{e.timestamp?.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Wireless devices */}
      {data.wireless_devices && data.wireless_devices.length > 0 && (
        <div className="pcap-card">
          <h3 className="pcap-card__title">Top Wireless Devices</h3>
          <div className="pcap-table-wrapper">
            <table className="pcap-table">
              <thead>
                <tr>
                  <th>MAC</th>
                  <th>Pacotes</th>
                  <th>Bytes</th>
                </tr>
              </thead>
              <tbody>
                {data.wireless_devices.map((d, i) => (
                  <tr key={i}>
                    <td className="pcap-table__mono">{d.mac}</td>
                    <td>{d.packets}</td>
                    <td>{formatBytes(d.bytes)}</td>
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
