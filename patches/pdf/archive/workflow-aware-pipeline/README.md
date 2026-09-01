# 流程级注入优化 (已归档, 11.96→5.42s -54.7%)

透明注入层 (.pth 单模块 pdf_accel): subprocess 拦截/20 进程合并、模板解析 memo、
原生尺寸渲染 (pdftoppm -scale-to)、双核 fill/render 流水线、PNG cl=1。
对特定流程有侵入 (识别脚本/跨调用缓存/按申请数建流水线), 不适用于新流程,
归档为极限性能参考。详见 docs/pdf-optimization-report.md。
镜像: ubuntu-document-bench:pdf-opt (j 机保留)。
