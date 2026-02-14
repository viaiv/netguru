/**
 * Tipos para dados estruturados de analise PCAP retornados pelo backend.
 * Estrutura espelha exatamente o dict retornado pela Celery task.
 */

export interface ITopTalker {
  ip: string;
  packets: number;
  bytes: number;
}

export interface IConversation {
  src: string;
  dst: string;
  packets: number;
  bytes: number;
}

export interface ITimeBucket {
  time_offset: number;
  packets: number;
  bytes: number;
  top_protocols: Record<string, number>;
}

export interface ITcpIssue {
  type: string;
  src: string;
  dst: string;
  seq?: number;
}

export interface IDeauthEvent {
  src: string;
  dst: string;
  reason: number;
  reason_text: string;
  timestamp: number;
}

export interface IWirelessDevice {
  mac: string;
  packets: number;
  bytes: number;
  type: string;
}

export interface IPcapAnalysisData {
  // Basic stats
  total_packets: number;
  duration_seconds: number;
  protocols: Record<string, number>;
  top_talkers: ITopTalker[];
  conversations: IConversation[];
  anomalies: string[];
  dns_queries: string[];
  tcp_issues: ITcpIssue[];
  network_protocols: string[];

  // Bandwidth & time-series
  total_bytes: number;
  avg_throughput_bps: number;
  peak_throughput_bps: number;
  frame_size_stats: {
    min: number;
    max: number;
    avg: number;
    median: number;
  };
  frame_size_distribution: Record<string, number>;
  time_buckets: ITimeBucket[];
  bucket_width_seconds: number;

  // HTTP
  http_methods: Record<string, number>;
  http_status_codes: Record<string, number>;
  http_urls: string[];
  http_hosts: string[];
  http_request_count: number;
  http_response_count: number;

  // TLS
  tls_versions: Record<string, number>;
  tls_sni_hosts: string[];
  tls_cipher_suites: string[];
  tls_handshakes: Record<string, number>;

  // VoIP/SIP
  voip_sip_methods: Record<string, number>;
  voip_sip_responses: Record<string, number>;
  voip_rtp_streams: number;
  voip_rtp_codecs: string[];

  // Wireless (802.11)
  is_wireless: boolean;
  wireless_frame_types: Record<string, number>;
  deauth_events: IDeauthEvent[];
  disassoc_events: IDeauthEvent[];
  retry_stats: {
    total_frames: number;
    retries: number;
    rate_pct: number;
  };
  signal_stats: {
    min_dBm: number;
    max_dBm: number;
    avg_dBm: number;
    median_dBm: number;
    samples: number;
  };
  channels: Record<string, number>;
  ssids: string[];
  wireless_devices: IWirelessDevice[];
}
