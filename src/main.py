import uvicorn
#entry point to run FastAPI app
if __name__ == "__main__":
    uvicorn.run(
        "src.webapp:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

