import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import EvidencePanel from './EvidencePanel';

describe('EvidencePanel', () => {
  it('renders confidence badge and expands evidence details', () => {
    render(
      <EvidencePanel
        metadata={{
          evidence: {
            items: [
              {
                id: 'tool:0',
                type: 'tool_call',
                source: 'search_rag_global',
                status: 'completed',
                strength: 'strong',
                summary: 'Tool search_rag_global retornou padrao Cisco.',
                details: {
                  input: 'ospf md5 authentication',
                  output: 'Use ip ospf message-digest-key 1 md5 <senha>',
                },
              },
            ],
            total_count: 1,
            strong_count: 1,
            medium_count: 0,
            weak_count: 0,
            failed_count: 0,
          },
          confidence: {
            score: 88,
            level: 'high',
            reasons: ['1 evidencia forte de ferramentas/fontes.'],
            warning: null,
          },
        }}
      />
    );

    expect(screen.getByText('Evidencias')).toBeInTheDocument();
    expect(screen.getByText(/Confianca alta/i)).toBeInTheDocument();
    expect(screen.queryByText('Input')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Ver evidencias \(1\)/i }));

    expect(screen.getByText('search_rag_global')).toBeInTheDocument();
    expect(screen.getByText('Input')).toBeInTheDocument();
    expect(screen.getByText('Output')).toBeInTheDocument();
    expect(screen.getByText('ospf md5 authentication')).toBeInTheDocument();
  });

  it('renders warning when confidence metadata indicates caution', () => {
    render(
      <EvidencePanel
        metadata={{
          evidence: {
            items: [],
            total_count: 0,
            strong_count: 0,
            medium_count: 0,
            weak_count: 0,
            failed_count: 0,
          },
          confidence: {
            score: 22,
            level: 'low',
            reasons: ['Nenhuma evidencia observavel foi registrada nesta resposta.'],
            warning: 'Sinal de cautela: faltam evidencias fortes.',
          },
        }}
      />
    );

    expect(screen.getByText(/Confianca baixa/i)).toBeInTheDocument();
    expect(screen.getByText(/Sinal de cautela/i)).toBeInTheDocument();
  });
});
