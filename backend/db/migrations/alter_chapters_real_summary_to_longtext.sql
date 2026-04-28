-- 将 chapters.real_summary 从 TEXT 扩展为 LONGTEXT
-- 目的：避免章节运行时数据、分阶段审批/优化摘要在 MySQL 中写入超长后触发
-- "Data too long for column 'real_summary'"。

ALTER TABLE chapters
    MODIFY COLUMN real_summary LONGTEXT NULL;
