module.exports = {
  apps: [
    {
      name: "nextjs",
      script: "bash",
      args: "-c 'npm run build && npm run start:next'", // Updated line
      log_file: "next_output.log",
      out_file: "next_output.log",
      error_file: "next_output.log",
      merge_logs: true,
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "fastapi",
      script: "bash",
      args: "-c 'pip install -r requirements.txt && python3 -m uvicorn api.index:app --port 8000 --timeout-keep-alive 120 --workers 4'",
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