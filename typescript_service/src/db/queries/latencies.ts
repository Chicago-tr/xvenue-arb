import { bigint } from "drizzle-orm/pg-core/index.js";
import { BinanceApi, CoinbaseApi } from "../../api.js";
import { db } from "../index.js";
import {
  exchanges,
  newPrices,
  prices,
  symbols,
  latency_metrics,
} from "../schema.js";
import {
  loadReferenceData,
  exchangeNameToId,
  symbolCodeToId,
} from "./prices.js";

export async function logLatency(record: {
  exchange: string;
  endpoint: string;
  symbol: string;
  clientSendTs: number;
  clientRecvTs: number;
  rttMs: number;
  statusCode: number;
  error?: string;
}) {
  // await loadReferenceData();
  // const exchange_id = exchangeNameToId.get(record.exchange);
  // const symbol_id = symbolCodeToId.get(record.symbol);

  // if (exchange_id == null || symbol_id == null) {
  //   throw new Error("Unknown exchange or symbol");
  // }
  await db
    .insert(latency_metrics)
    .values({
      exchange: record.exchange,
      endpoint: record.endpoint,
      symbol: record.symbol,
      client_send_ts: record.clientSendTs,
      client_recv_ts: record.clientRecvTs,
      rtt_ms: record.rttMs,
      status_code: record.statusCode,
      error: record.error || null,
    })
    .catch(console.error);
  //debugging:
  // console.log("Logging latency:", {
  //   exchange: record.exchange,
  //   endpoint: record.endpoint,
  //   rttMs: record.rttMs,
  //   statusCode: record.statusCode,
  // });
}
