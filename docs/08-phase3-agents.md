# Phase 3: Agents - NetGuru Platform

**Sprint:** 5-6 (2 semanas)  
**Objetivo:** Packet Buddy Agent + Topology Visualization  
**Data:** Março 2026

---

## 🎯 Objetivos da Fase 3

Ao final desta fase, teremos:
- ✅ Celery workers configurados
- ✅ Packet Buddy Agent (análise de PCAP)
- ✅ Config Parser (Cisco/Juniper)
- ✅ Topology Builder (CDP/LLDP → Graph)
- ✅ Visualização de topologia (React Flow)
- ✅ Config Validator Agent

**Entregável:** MVP completo com capacidades avançadas que diferenciam NetGuru de chatbots genéricos.

---

## 📋 Backend Implementation

### Task 3.1: Celery Setup

**backend/requirements.txt (adicionar):**
```txt
celery[redis]==5.3.4
flower==2.0.1
scapy==2.5.0
pyshark==0.6
networkx==3.2.1
```

---

**app/workers/celery_app.py:**
```python
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "netguru_workers",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=270,  # 4.5 minutes
)

celery_app.conf.task_routes = {
    "app.workers.tasks.pcap_tasks.*": {"queue": "pcap"},
    "app.workers.tasks.rag_tasks.*": {"queue": "rag"},
    "app.workers.tasks.topology_tasks.*": {"queue": "topology"},
}
```

**docker-compose.yml (adicionar):**
```yaml
  celery_worker:
    build: ./backend
    command: celery -A app.workers.celery_app worker --loglevel=info -Q pcap,rag,topology
    volumes:
      - ./backend:/app
      - ./uploads:/uploads
    env_file:
      - ./backend/.env
    depends_on:
      - redis
      - postgres
  
  flower:
    build: ./backend
    command: celery -A app.workers.celery_app flower --port=5555
    ports:
      - "5555:5555"
    env_file:
      - ./backend/.env
    depends_on:
      - redis
```

---

### Task 3.2: PCAP Analyzer Service

**app/services/pcap_analyzer.py:**
```python
from scapy.all import rdpcap, IP, TCP, UDP
from typing import Dict, List
from collections import defaultdict
import os

class PCAPAnalyzer:
    def __init__(self, max_packets: int = 100_000):
        self.max_packets = max_packets
    
    def analyze(self, file_path: str) -> Dict:
        """
        Analisa arquivo PCAP e retorna estatísticas
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PCAP file not found: {file_path}")
        
        packets = rdpcap(file_path, count=self.max_packets)
        
        results = {
            "total_packets": len(packets),
            "protocols": self._analyze_protocols(packets),
            "top_talkers": self._analyze_top_talkers(packets),
            "retransmissions": self._analyze_retransmissions(packets),
            "latency_stats": self._analyze_latency(packets)
        }
        
        return results
    
    def _analyze_protocols(self, packets) -> Dict[str, int]:
        """Conta pacotes por protocolo"""
        protocols = defaultdict(int)
        
        for pkt in packets:
            if IP in pkt:
                if TCP in pkt:
                    protocols['TCP'] += 1
                elif UDP in pkt:
                    protocols['UDP'] += 1
                else:
                    protocols['Other'] += 1
        
        return dict(protocols)
    
    def _analyze_top_talkers(self, packets) -> List[Dict]:
        """Identifica IPs que mais trocam pacotes"""
        talkers = defaultdict(int)
        
        for pkt in packets:
            if IP in pkt:
                src = pkt[IP].src
                dst = pkt[IP].dst
                talkers[src] += 1
                talkers[dst] += 1
        
        # Top 10
        sorted_talkers = sorted(talkers.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return [
            {"ip": ip, "packet_count": count}
            for ip, count in sorted_talkers
        ]
    
    def _analyze_retransmissions(self, packets) -> Dict:
        """Detecta retransmissões TCP"""
        seen_packets = set()
        retransmissions = 0
        
        for pkt in packets:
            if TCP in pkt and IP in pkt:
                # Simple heuristic: same src, dst, seq number
                key = (
                    pkt[IP].src,
                    pkt[IP].dst,
                    pkt[TCP].sport,
                    pkt[TCP].dport,
                    pkt[TCP].seq
                )
                
                if key in seen_packets:
                    retransmissions += 1
                else:
                    seen_packets.add(key)
        
        return {
            "total_retransmissions": retransmissions,
            "retransmission_rate": retransmissions / len(packets) if packets else 0
        }
    
    def _analyze_latency(self, packets) -> Dict:
        """Calcula estatísticas de latência (aproximadas via timestamps)"""
        if len(packets) < 2:
            return {"avg_interpacket_time_ms": 0}
        
        times = []
        for i in range(1, len(packets)):
            delta = float(packets[i].time - packets[i-1].time) * 1000  # ms
            times.append(delta)
        
        avg_time = sum(times) / len(times)
        
        return {
            "avg_interpacket_time_ms": round(avg_time, 3),
            "min_time_ms": round(min(times), 3),
            "max_time_ms": round(max(times), 3)
        }
```

---

### Task 3.3: Celery PCAP Task

**app/workers/tasks/pcap_tasks.py:**
```python
from app.workers.celery_app import celery_app
from app.services.pcap_analyzer import PCAPAnalyzer
from app.db.session import AsyncSessionLocal
from app.models.document import Document
from sqlalchemy import select
from datetime import datetime
import uuid

@celery_app.task(bind=True, max_retries=3)
def analyze_pcap_task(self, document_id: str):
    """
    Celery task para analisar PCAP
    """
    try:
        # Get document from DB
        async def get_document():
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Document).where(Document.id == uuid.UUID(document_id))
                )
                return result.scalar_one_or_none()
        
        import asyncio
        document = asyncio.run(get_document())
        
        if not document:
            return {"error": "Document not found"}
        
        # Update status
        async def update_status(status: str, metadata: dict = None):
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Document).where(Document.id == uuid.UUID(document_id))
                )
                doc = result.scalar_one()
                doc.status = status
                if metadata:
                    doc.metadata = metadata
                if status == "completed":
                    doc.processed_at = datetime.utcnow()
                await db.commit()
        
        asyncio.run(update_status("processing"))
        
        # Analyze
        analyzer = PCAPAnalyzer()
        result = analyzer.analyze(document.storage_path)
        
        # Save result
        asyncio.run(update_status("completed", result))
        
        return result
        
    except Exception as exc:
        # Update status to failed
        async def mark_failed(error_msg: str):
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Document).where(Document.id == uuid.UUID(document_id))
                )
                doc = result.scalar_one()
                doc.status = "failed"
                doc.metadata = {"error": error_msg}
                await db.commit()
        
        import asyncio
        asyncio.run(mark_failed(str(exc)))
        
        # Retry
        raise self.retry(exc=exc, countdown=60)
```

---

### Task 3.4: Config Parser Service

**app/services/config_parser.py:**
```python
from typing import List, Dict
import re

class CiscoConfigParser:
    def parse(self, config_text: str) -> Dict:
        """
        Parse Cisco IOS config e extrai informações estruturadas
        """
        sections = self._split_sections(config_text)
        
        return {
            "hostname": self._extract_hostname(config_text),
            "interfaces": self._extract_interfaces(sections),
            "routing": self._extract_routing(sections),
            "acls": self._extract_acls(config_text)
        }
    
    def _split_sections(self, config: str) -> List[Dict]:
        """Divide config em seções (interfaces, routers, etc)"""
        sections = []
        current_section = []
        current_type = "global"
        
        for line in config.split('\n'):
            stripped = line.strip()
            
            if stripped.startswith('interface '):
                if current_section:
                    sections.append({"type": current_type, "lines": current_section})
                current_type = "interface"
                current_section = [stripped]
            
            elif stripped.startswith('router '):
                if current_section:
                    sections.append({"type": current_type, "lines": current_section})
                current_type = "routing"
                current_section = [stripped]
            
            elif stripped and not stripped.startswith('!'):
                current_section.append(stripped)
        
        if current_section:
            sections.append({"type": current_type, "lines": current_section})
        
        return sections
    
    def _extract_hostname(self, config: str) -> str:
        """Extrai hostname"""
        match = re.search(r'hostname\s+(\S+)', config)
        return match.group(1) if match else "Unknown"
    
    def _extract_interfaces(self, sections: List[Dict]) -> List[Dict]:
        """Extrai configurações de interfaces"""
        interfaces = []
        
        for section in sections:
            if section['type'] == 'interface':
                lines = section['lines']
                iface_name = lines[0].split()[1]
                
                iface_config = {"name": iface_name, "config": {}}
                
                for line in lines[1:]:
                    if 'ip address' in line:
                        parts = line.split()
                        iface_config['config']['ip_address'] = parts[2]
                        iface_config['config']['subnet_mask'] = parts[3]
                    elif 'description' in line:
                        iface_config['config']['description'] = ' '.join(line.split()[1:])
                
                interfaces.append(iface_config)
        
        return interfaces
    
    def _extract_routing(self, sections: List[Dict]) -> List[Dict]:
        """Extrai configurações de roteamento"""
        routing = []
        
        for section in sections:
            if section['type'] == 'routing':
                protocol = section['lines'][0].split()[1]
                routing.append({
                    "protocol": protocol,
                    "config": section['lines']
                })
        
        return routing
    
    def _extract_acls(self, config: str) -> List[Dict]:
        """Extrai ACLs"""
        acls = []
        acl_pattern = r'access-list\s+(\d+)\s+(.+)'
        
        for match in re.finditer(acl_pattern, config):
            acls.append({
                "number": match.group(1),
                "rule": match.group(2)
            })
        
        return acls
```

---

### Task 3.5: Topology Builder Service

**app/services/topology_builder.py:**
```python
from typing import List, Dict
import networkx as nx
from app.services.config_parser import CiscoConfigParser

class TopologyBuilder:
    def __init__(self):
        self.parser = CiscoConfigParser()
        self.graph = nx.Graph()
    
    def build_from_configs(self, configs: List[Dict]) -> Dict:
        """
        Constrói grafo de topologia a partir de configs
        
        Args:
            configs: List[{"filename": str, "content": str}]
        
        Returns:
            Graph data no formato React Flow
        """
        devices = []
        
        # Parse cada config
        for config_data in configs:
            parsed = self.parser.parse(config_data['content'])
            hostname = parsed['hostname']
            
            device = {
                "id": hostname,
                "type": self._infer_device_type(parsed),
                "data": {
                    "label": hostname,
                    "interfaces": parsed['interfaces']
                }
            }
            devices.append(device)
            
            # Add node to graph
            self.graph.add_node(hostname, **device)
        
        # Infer connections (baseado em subnets comuns)
        edges = self._infer_connections(devices)
        
        # Convert to React Flow format
        return self._to_react_flow_format(devices, edges)
    
    def _infer_device_type(self, parsed_config: Dict) -> str:
        """Infere tipo de dispositivo baseado na config"""
        routing = parsed_config.get('routing', [])
        
        if routing:
            return "router"
        
        interfaces = parsed_config.get('interfaces', [])
        if len(interfaces) > 4:
            return "switch"
        
        return "unknown"
    
    def _infer_connections(self, devices: List[Dict]) -> List[Dict]:
        """
        Infere conexões baseado em interfaces na mesma subnet
        """
        edges = []
        
        # Build subnet map
        subnet_map = {}
        for device in devices:
            for iface in device['data']['interfaces']:
                ip = iface['config'].get('ip_address')
                if ip:
                    # Simplificado: apenas /24
                    subnet = '.'.join(ip.split('.')[:3])
                    if subnet not in subnet_map:
                        subnet_map[subnet] = []
                    subnet_map[subnet].append({
                        "device": device['id'],
                        "interface": iface['name']
                    })
        
        # Create edges for devices in same subnet
        edge_id = 1
        for subnet, members in subnet_map.items():
            if len(members) >= 2:
                # Connect first two (simplificado)
                edges.append({
                    "id": f"e{edge_id}",
                    "source": members[0]['device'],
                    "target": members[1]['device'],
                    "label": f"{members[0]['interface']} ↔ {members[1]['interface']}",
                    "data": {"subnet": subnet}
                })
                edge_id += 1
        
        return edges
    
    def _to_react_flow_format(self, devices: List[Dict], edges: List[Dict]) -> Dict:
        """
        Converte para formato React Flow
        """
        nodes = []
        
        # Layout simples (grid)
        cols = 3
        for i, device in enumerate(devices):
            row = i // cols
            col = i % cols
            
            nodes.append({
                "id": device['id'],
                "type": device['type'],
                "data": device['data'],
                "position": {
                    "x": col * 300 + 50,
                    "y": row * 200 + 50
                }
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "total_devices": len(devices),
                "device_types": {
                    "router": sum(1 for d in devices if d['type'] == 'router'),
                    "switch": sum(1 for d in devices if d['type'] == 'switch')
                }
            }
        }
```

---

### Task 3.6: Topology Endpoints

**app/api/v1/endpoints/topology.py:**
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.document import Document
from app.models.topology import TopologySnapshot
from app.services.topology_builder import TopologyBuilder
from app.schemas.topology import TopologyCreate, TopologyResponse
from typing import List
import uuid

router = APIRouter()

@router.post("/generate", response_model=TopologyResponse)
async def generate_topology(
    data: TopologyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Gera topologia a partir de configs uploaded
    """
    # Get documents
    result = await db.execute(
        select(Document).where(
            Document.id.in_(data.file_ids),
            Document.user_id == current_user.id,
            Document.file_type == "config"
        )
    )
    documents = result.scalars().all()
    
    if len(documents) != len(data.file_ids):
        raise HTTPException(400, "Some files not found or not configs")
    
    # Read configs
    configs = []
    for doc in documents:
        with open(doc.storage_path, 'r') as f:
            configs.append({
                "filename": doc.filename,
                "content": f.read()
            })
    
    # Build topology
    builder = TopologyBuilder()
    graph_data = builder.build_from_configs(configs)
    
    # Save snapshot
    snapshot = TopologySnapshot(
        user_id=current_user.id,
        title=data.title or f"Topologia - {len(documents)} devices",
        graph_data=graph_data,
        metadata=graph_data.get('metadata', {})
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    
    return snapshot

@router.get("/{topology_id}", response_model=TopologyResponse)
async def get_topology(
    topology_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(TopologySnapshot).where(
            TopologySnapshot.id == topology_id,
            TopologySnapshot.user_id == current_user.id
        )
    )
    topology = result.scalar_one_or_none()
    
    if not topology:
        raise HTTPException(404, "Topology not found")
    
    return topology
```

---

## 📋 Frontend Implementation

### Task 3.7: Topology Visualization

**frontend/package.json (adicionar):**
```json
{
  "dependencies": {
    "reactflow": "^11.10.1"
  }
}
```

---

**src/pages/Topology.tsx:**
```typescript
import React, { useEffect, useState } from 'react';
import ReactFlow, { 
  Node, 
  Edge, 
  Background, 
  Controls, 
  MiniMap 
} from 'reactflow';
import 'reactflow/dist/style.css';
import api from '../services/api';
import { useParams } from 'react-router-dom';

interface TopologyData {
  nodes: Node[];
  edges: Edge[];
  metadata: {
    total_devices: number;
    device_types: Record<string, number>;
  };
}

export default function Topology() {
  const { id } = useParams();
  const [topology, setTopology] = useState<TopologyData | null>(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    loadTopology();
  }, [id]);
  
  const loadTopology = async () => {
    try {
      const response = await api.get(`/topology/${id}`);
      setTopology(response.data.graph_data);
    } catch (error) {
      console.error('Failed to load topology:', error);
    } finally {
      setLoading(false);
    }
  };
  
  if (loading) {
    return <div className="flex items-center justify-center h-screen">Loading...</div>;
  }
  
  if (!topology) {
    return <div className="flex items-center justify-center h-screen">Topology not found</div>;
  }
  
  return (
    <div className="h-screen flex flex-col">
      <div className="bg-white border-b p-4">
        <h1 className="text-2xl font-bold">Network Topology</h1>
        <p className="text-gray-600">
          {topology.metadata.total_devices} devices
        </p>
      </div>
      
      <div className="flex-1">
        <ReactFlow
          nodes={topology.nodes}
          edges={topology.edges}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
    </div>
  );
}
```

---

### Task 3.8: PCAP Analysis Page

**src/pages/PCAPAnalysis.tsx:**
```typescript
import React, { useState } from 'react';
import api from '../services/api';

export default function PCAPAnalysis() {
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  
  const handleUpload = async () => {
    if (!file) return;
    
    setLoading(true);
    
    try {
      // Upload file
      const formData = new FormData();
      formData.append('file', file);
      formData.append('file_type', 'pcap');
      
      const uploadResponse = await api.post('/files/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      const fileId = uploadResponse.data.id;
      
      // Start analysis
      const analysisResponse = await api.post('/analysis/pcap', {
        file_id: fileId,
        analysis_type: 'full'
      });
      
      const taskId = analysisResponse.data.task_id;
      
      // Poll for result
      await pollTaskStatus(taskId);
      
    } catch (error) {
      console.error('Analysis failed:', error);
    }
  };
  
  const pollTaskStatus = async (taskId: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await api.get(`/analysis/tasks/${taskId}`);
        
        if (response.data.status === 'completed') {
          setAnalysis(response.data.result);
          setLoading(false);
          clearInterval(interval);
        } else if (response.data.status === 'failed') {
          console.error('Analysis failed:', response.data.error_message);
          setLoading(false);
          clearInterval(interval);
        }
      } catch (error) {
        console.error('Polling failed:', error);
        clearInterval(interval);
      }
    }, 2000);
  };
  
  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6">PCAP Analysis</h1>
      
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Upload PCAP File</h2>
        
        <input
          type="file"
          accept=".pcap,.pcapng,.cap"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="mb-4"
        />
        
        <button
          onClick={handleUpload}
          disabled={!file || loading}
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Analyzing...' : 'Analyze'}
        </button>
      </div>
      
      {analysis && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Analysis Results</h2>
          
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="bg-gray-50 p-4 rounded">
              <p className="text-sm text-gray-600">Total Packets</p>
              <p className="text-2xl font-bold">{analysis.total_packets}</p>
            </div>
            
            <div className="bg-gray-50 p-4 rounded">
              <p className="text-sm text-gray-600">Retransmissions</p>
              <p className="text-2xl font-bold">{analysis.retransmissions.total_retransmissions}</p>
            </div>
          </div>
          
          <div className="mb-6">
            <h3 className="text-lg font-semibold mb-2">Top Talkers</h3>
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left">IP Address</th>
                  <th className="px-4 py-2 text-left">Packets</th>
                </tr>
              </thead>
              <tbody>
                {analysis.top_talkers.map((talker: any, i: number) => (
                  <tr key={i} className="border-t">
                    <td className="px-4 py-2">{talker.ip}</td>
                    <td className="px-4 py-2">{talker.packet_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
```

---

## ✅ Definition of Done

Fase 3 está completa quando:

- [ ] Celery workers rodando (`docker-compose up`)
- [ ] Upload de PCAP funciona
- [ ] Task de análise é criada e processada
- [ ] Frontend mostra resultados de análise
- [ ] Upload de configs funciona
- [ ] Topologia é gerada corretamente
- [ ] Visualização React Flow renderiza topologia
- [ ] Usuário pode navegar e zoom na topologia
- [ ] Flower UI acessível em localhost:5555

---

## 🧪 Testes

```bash
# Testar PCAP analyzer
pytest tests/test_pcap_analyzer.py -v

# Testar config parser
pytest tests/test_config_parser.py -v

# Testar topology builder
pytest tests/test_topology_builder.py -v

# Testar Celery tasks (requer Redis)
pytest tests/test_celery_tasks.py -v
```

---

## 🗺️ Próximos Passos

Fase 3 completa? MVP está pronto!

Próximos passos:
- **[09-deployment.md](09-deployment.md)**: Deploy em produção
- **[10-testing-strategy.md](10-testing-strategy.md)**: Testes E2E completos
- **Feedback**: Coletar feedback de early adopters
- **Iteração**: Melhorias baseadas em uso real

**Estimativa de tempo:** 12-14 dias (2 desenvolvedores)

---

**🎉 Parabéns! Com as 3 fases completas, o MVP do NetGuru está funcional!**
