module.exports = {
  apps: [
    {
      name: "nextjs-test",
      script: "bash",
      args: "-c 'npm run build && npm run start:next'", 
      log_file: "next_output.log",
      out_file: "next_output.log",
      error_file: "next_output.log",
      merge_logs: true,
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "fastapi-test",
      script: "bash",
      args: "-c 'pip install -r requirements.txt && python3 -m uvicorn api.index:app --port 8001 --timeout-keep-alive 120 --workers 4'",
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