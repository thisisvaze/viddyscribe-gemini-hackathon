module.exports = {
    apps: [
      {
        name: "nextjs-fastapi",
        script: "npm",
        args: "run start:concurrent",
        log_file: "output.log",
        out_file: "output.log",
        error_file: "output.log",
        merge_logs: true,
        env: {
          NODE_ENV: "production",
        },
      },
    ],
  };