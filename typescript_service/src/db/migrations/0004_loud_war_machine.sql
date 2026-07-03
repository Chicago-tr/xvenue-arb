CREATE TABLE "latency_metrics" (
	"id" serial PRIMARY KEY NOT NULL,
	"exchange" varchar(50) NOT NULL,
	"endpoint" varchar(200) NOT NULL,
	"symbol" varchar(20),
	"client_send_ts" bigint NOT NULL,
	"client_recv_ts" bigint NOT NULL,
	"rtt_ms" real NOT NULL,
	"status_code" integer NOT NULL,
	"error" varchar(200),
	"ingested_at" timestamp DEFAULT now() NOT NULL
);
