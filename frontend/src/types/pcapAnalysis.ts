/**
 * Tipos para dados estruturados de analise PCAP retornados pelo backend.
 */

export interface IProtocolEntry {
  protocol: string;
  count: number;
  percentage: number;
}

export interface ITopTalker {
  ip: string;
  packets: number;
  bytes: number;
}

export interface IConversation {
  src: string;
  dst: string;
  protocol: string;
  packets: number;
  bytes: number;
}

export interface IAnomaly {
  type: string;
  severity: 'info' | 'warning' | 'critical';
  description: string;
  details?: string;
}

export interface ITimeBucket {
  timestamp: string;
  packets: number;
  bytes: number;
}

export interface IFrameSize {
  range: string;
  count: number;
}

export interface IDnsQuery {
  query: string;
  type: string;
  count: number;
}

export interface ITcpIssues {
  retransmissions: number;
  rst_count: number;
  zero_window: number;
}

export interface IRoutingProtocols {
  ospf: number;
  bgp: number;
  eigrp: number;
  hsrp: number;
}

export interface IBandwidthStats {
  total_bytes: number;
  duration_seconds: number;
  avg_bps: number;
  peak_bps: number;
}

export interface IHttpAnalysis {
  methods: Record<string, number>;
  status_codes: Record<string, number>;
  top_urls: Array<{ url: string; count: number }>;
  top_hosts: Array<{ host: string; count: number }>;
}

export interface ITlsAnalysis {
  versions: Record<string, number>;
  sni_hosts: Array<{ host: string; count: number }>;
  cipher_suites: Array<{ cipher: string; count: number }>;
}

export interface IVoipAnalysis {
  sip_methods: Record<string, number>;
  sip_responses: Record<string, number>;
  rtp_streams: number;
  rtp_codecs: string[];
}

export interface IWirelessFrameTypes {
  management: number;
  control: number;
  data: number;
}

export interface IDeauthEvent {
  src: string;
  dst: string;
  reason_code: number;
  reason_text: string;
  count: number;
}

export interface IWirelessAnalysis {
  frame_types: IWirelessFrameTypes;
  deauth_events: IDeauthEvent[];
  retry_rate: number;
  signal_stats: {
    min_dbm: number;
    max_dbm: number;
    avg_dbm: number;
  };
  channels: Record<string, number>;
  ssids: string[];
}

export interface IPcapAnalysisData {
  total_packets: number;
  capture_duration: number;
  is_wireless: boolean;
  protocols: IProtocolEntry[];
  top_talkers: ITopTalker[];
  conversations: IConversation[];
  anomalies: IAnomaly[];
  time_buckets: ITimeBucket[];
  frame_sizes: IFrameSize[];
  dns_queries: IDnsQuery[];
  tcp_issues: ITcpIssues;
  routing_protocols: IRoutingProtocols;
  bandwidth: IBandwidthStats;
  http?: IHttpAnalysis;
  tls?: ITlsAnalysis;
  voip?: IVoipAnalysis;
  wireless?: IWirelessAnalysis;
}
