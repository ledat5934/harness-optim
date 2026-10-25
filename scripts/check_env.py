import importlib, sys, glob, os
for m in sys.argv[1:]:
    try:
        mod = importlib.import_module(m); print("OK", m, getattr(mod, "__version__", ""))
    except Exception as e:
        print("FAIL", m, type(e).__name__, e)
print("jars:", glob.glob(os.path.join(sys.prefix, "lib/python3.12/site-packages/pyserini/resources/jars/*")))
