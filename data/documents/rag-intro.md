# 什么是 RAG

RAG 的全称是 Retrieval-Augmented Generation，即检索增强生成。

RAG 会先从知识库中检索与用户问题相关的内容，
再将检索结果提供给大语言模型，帮助模型生成答案。

RAG 的核心流程包括文档加载、文本切分、向量化、
检索相关内容和生成答案。

# 什么是 Embedding

Embedding 是将文本转换成向量的技术。
向量可以用于衡量不同文本在语义上的相似程度。
