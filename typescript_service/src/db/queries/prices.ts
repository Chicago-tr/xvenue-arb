import { BinanceApi, CoinbaseApi } from "../../api.js";
import { db } from "../index.js";
import { exchanges, newPrices, prices, symbols } from "../schema.js";

export const exchangeNameToId = new Map<string, number>();
export const symbolCodeToId = new Map<string, number>();

export async function loadReferenceData() {
  //This function queries the database tables and inserts a name/symbol-id pair into constant variables
  //The variables are used to get the table id of an exchange name or symbol when creating a price entry
  //Data for the exchange and symbol tables is currently hardcoded since it's just names
  const exchangeData = await db
    .select({ id: exchanges.id, name: exchanges.exchange_name })
    .from(exchanges);
  for (let row of exchangeData) {
    if (row.name) {
      exchangeNameToId.set(row.name, row.id);
    } else {
      throw new Error("Failed to load an exchange name for reference.");
    }
  }

  const symbolsData = await db
    .select({ id: symbols.id, symbol_code: symbols.symbol_code })
    .from(symbols);
  for (let row of symbolsData) {
    if (row.symbol_code) {
      symbolCodeToId.set(row.symbol_code, row.id);
    } else {
      throw new Error("Failed to load a symbol code for reference.");
    }
  }
}

export async function createPriceEntry(
  exchangeName: string,
  symbol: string,
  bid: number,
  ask: number,
) {
  if (exchangeNameToId.size === 0 || symbolCodeToId.size === 0) {
    await loadReferenceData();
  }

  const exchange_id = exchangeNameToId.get(exchangeName);
  const symbol_id = symbolCodeToId.get(symbol);

  if (exchange_id == null || symbol_id == null) {
    throw new Error("Unknown exchange or symbol");
  }
  await db.insert(prices).values({
    exchange_id: exchange_id,
    symbol_id: symbol_id,
    bid: bid,
    ask: ask,
  });
}

const CoinApi = new CoinbaseApi();
const BinApi = new BinanceApi();

export async function insertBinancePrice(symbol: string) {
  const data = await BinApi.fetchPrice(symbol);
  if (!data) return;
  await createPriceEntry("Binance", symbol, data.bid, data.ask);
}

export async function insertCoinbasePrice(symbol: string) {
  const data = await CoinApi.fetchPrice(symbol);
  if (!data) return;
  await createPriceEntry("Coinbase", symbol, data.bid, data.ask);
}
