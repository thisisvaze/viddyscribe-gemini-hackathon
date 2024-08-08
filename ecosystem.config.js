module.exports = {
  apps: [
    {
      name: "nextjs",
      script: "npm",
      args: "run dev",
      log_file: "next_output.log",
      out_file: "next_output.log",
      error_file: "next_output.log",
      merge_logs: true,
      env: {
        NODE_ENV: "development",
      },
    },
    {
      name: "fastapi",
      script: "bash",
      args: "-c 'source activate gpu && python -m uvicorn api.index:app --port 8001 --timeout-keep-alive 120'",
      log_file: "fastapi_output.log",
      out_file: "fastapi_output.log",
      error_file: "fastapi_output.log",
      merge_logs: true,
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};