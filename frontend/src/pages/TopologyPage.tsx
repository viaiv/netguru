import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { api } from '../services/api';

interface TopologyData {
  id: string;
  title: string;
  source_type: string;
  nodes: Node[];
  edges: Edge[];
  summary: string | null;
  metadata: {
    device_count: number;
    link_count: number;
    vendors: string[];
  } | null;
  created_at: string;
}

function TopologyPage() {
  const { topologyId } = useParams<{ topologyId: string }>();
  const navigate = useNavigate();
  const [topology, setTopology] = useState<TopologyData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (!topologyId) return;
    async function load() {
      try {
        const { data } = await api.get<TopologyData>(`/topology/${topologyId}`);
        setTopology(data);
        setNodes(data.nodes);
        setEdges(data.edges);
      } catch {
        setError('Topologia nao encontrada ou sem permissao.');
      } finally {
        setIsLoading(false);
      }
    }
    void load();
  }, [topologyId, setNodes, setEdges]);

  const onInit = useCallback(() => {
    // Auto-fit on load handled by React Flow
  }, []);

  if (isLoading) {
    return (
      <section className="view" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ color: 'var(--ink-soft)' }}>Carregando topologia...</p>
      </section>
    );
  }

  if (error || !topology) {
    return (
      <section className="view" style={{ textAlign: 'center', paddingTop: '3rem' }}>
        <p style={{ color: 'var(--ink-soft)' }}>{error || 'Topologia nao encontrada.'}</p>
        <button type="button" className="btn btn-outline" style={{ marginTop: '1rem' }} onClick={() => navigate(-1)}>
          Voltar
        </button>
      </section>
    );
  }

  return (
    <section className="view topology-view">
      <div className="topology-header">
        <div>
          <h2 className="view-title">{topology.title}</h2>
          {topology.summary && (
            <p className="view-subtitle">{topology.summary}</p>
          )}
        </div>
        <div className="topology-stats">
          {topology.metadata && (
            <>
              <span className="chip">{topology.metadata.device_count} dispositivos</span>
              <span className="chip">{topology.metadata.link_count} links</span>
              {topology.metadata.vendors.map((v) => (
                <span key={v} className="chip chip-live">{v}</span>
              ))}
            </>
          )}
        </div>
      </div>

      <div className="topology-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onInit={onInit}
          fitView
          attributionPosition="bottom-left"
        >
          <Background />
          <Controls />
          <MiniMap
            nodeStrokeWidth={3}
            zoomable
            pannable
          />
        </ReactFlow>
      </div>
    </section>
  );
}

export default TopologyPage;
