package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const (
	queueKey        = "tahseen:queue"
	resultKeyPrefix = "tahseen:result:"
	resultTTL       = 1 * time.Hour
)

type CheckRequest struct {
	Text string `json:"text"`
}

type CheckResponse struct {
	JobID string `json:"job_id"`
}

type ResultResponse struct {
	JobID     string `json:"job_id"`
	Status    string `json:"status"`
	Result    string `json:"result,omitempty"`
	Error     string `json:"error,omitempty"`
	CreatedAt string `json:"created_at"`
}

var rdb *redis.Client

func main() {
	ctx := context.Background()
	shutdown, logger := initOTel(ctx, "tahseen-api")
	defer shutdown()
	slog.SetDefault(logger)

	redisAddr := os.Getenv("REDIS_ADDR")
	if redisAddr == "" {
		redisAddr = "localhost:6379"
	}

	rdb = redis.NewClient(&redis.Options{Addr: redisAddr})

	redisCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := rdb.Ping(redisCtx).Err(); err != nil {
		slog.Error("failed to connect to redis", "error", err)
		os.Exit(1)
	}
	slog.Info("connected to redis", "addr", redisAddr)

	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Recoverer)

	r.Get("/health", handleHealth)
	r.Post("/check", handleCheck)
	r.Get("/result/{id}", handleResult)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	slog.Info("starting server", "port", port)
	if err := http.ListenAndServe(":"+port, otelhttp.NewHandler(r, "tahseen-api")); err != nil {
		slog.Error("server error", "error", err)
		os.Exit(1)
	}
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func handleCheck(w http.ResponseWriter, r *http.Request) {
	var req CheckRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.Text == "" {
		http.Error(w, `{"error":"invalid request, text is required"}`, http.StatusBadRequest)
		return
	}

	jobID := uuid.New().String()
	job := map[string]string{
		"job_id":     jobID,
		"text":       req.Text,
		"created_at": time.Now().UTC().Format(time.RFC3339),
	}

	jobJSON, _ := json.Marshal(job)

	ctx := r.Context()

	rdb.HSet(ctx, resultKeyPrefix+jobID, map[string]string{
		"job_id":     jobID,
		"status":     "queued",
		"created_at": job["created_at"],
	})
	rdb.Expire(ctx, resultKeyPrefix+jobID, resultTTL)

	if err := rdb.LPush(ctx, queueKey, jobJSON).Err(); err != nil {
		slog.ErrorContext(ctx, "failed to enqueue job", "job_id", jobID, "error", err)
		http.Error(w, `{"error":"failed to enqueue job"}`, http.StatusInternalServerError)
		return
	}

	slog.InfoContext(ctx, "job enqueued", "job_id", jobID)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(CheckResponse{JobID: jobID})
}

func handleResult(w http.ResponseWriter, r *http.Request) {
	jobID := chi.URLParam(r, "id")

	ctx := r.Context()
	data, err := rdb.HGetAll(ctx, resultKeyPrefix+jobID).Result()
	if err != nil || len(data) == 0 {
		http.Error(w, `{"error":"job not found"}`, http.StatusNotFound)
		return
	}

	resp := ResultResponse{
		JobID:     data["job_id"],
		Status:    data["status"],
		Result:    data["result"],
		Error:     data["error"],
		CreatedAt: data["created_at"],
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}
