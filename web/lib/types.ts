import type { Citation } from "./citations";

export type { Citation };

export interface Sentence {
  text: string;
  kept: boolean;
  reason: string | null;
  support: number;
  citations: Citation[];
}

export interface AskDone {
  thread_id: string;
  refused: boolean;
  answer: string | null;
  dropped: Record<string, number>;
  provider: string | null;
  model: string | null;
  fallback_reason: string | null;
}

export interface ReindexRequest {
  action: string;
  target?: string | null;
  reason?: string | null;
  [key: string]: unknown;
}

export interface RepoRow {
  full_name: string;
  description: string | null;
  language: string | null;
  stars: number;
  html_url: string;
  default_branch: string;
  tree_sha: string | null;
  files: number;
  chunks: number;
  bytes: number;
  last_indexed_at: string | null;
}

export interface IndexRun {
  id: number;
  owner: string;
  trigger: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  chunks_written: number;
  error: string | null;
}

export interface WebhookHealth {
  configured: boolean;
  enabled: boolean;
  deliveries: number;
  last_delivery_at: string | null;
  last_repo: string | null;
}

export interface Corpus {
  version: string;
  readonly: boolean;
  rate_limit_per_minute: number;
  demo_note: string | null;
  owner: string;
  repo_count: number;
  file_count: number;
  chunk_count: number;
  bytes_indexed: number;
  embed_model: string;
  embed_dim: number;
  rerank_model: string | null;
  generation: string;
  webhook: WebhookHealth;
  last_index_run: IndexRun | null;
  repos: RepoRow[];
}

export interface RetrievalArm {
  "recall@5": number;
  "MRR@10": number;
  questions: number;
}

export interface InjectionCase {
  id: string;
  question: string;
  refused: boolean;
  complied: boolean;
  matched: string[];
  answer: string;
}

export interface EvalReport {
  generated_at: string;
  provider: string;
  corpus: {
    repo_count: number;
    file_count: number;
    chunk_count: number;
    embed_model: string;
    rerank_model: string | null;
  };
  retrieval: Record<string, RetrievalArm>;
  answers: {
    answerable: number;
    questions: number;
    skipped_not_indexed: number;
    answered: number;
    refused: number;
    refusal_errors: number;
    citations_total: number;
    citations_valid: number;
    citation_validity: number;
    sentences_without_citation: number;
  };
  injection: {
    probes: number;
    complied: number;
    cases: InjectionCase[];
  };
}
