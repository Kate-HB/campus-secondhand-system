-- ================================
-- 校园二手交易系统数据库（修复版）
-- 数据库名：ershousystem
-- 完全可执行顺序，已解决外键依赖问题
-- ================================

CREATE DATABASE IF NOT EXISTS ershousystem 
  DEFAULT CHARACTER SET utf8mb4 
  COLLATE utf8mb4_unicode_ci;
USE ershousystem;

-- 第1步：先创建不依赖任何表的表
CREATE TABLE user (
    user_id         BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
    account         VARCHAR(30) NOT NULL UNIQUE COMMENT '登录账号',
    password        VARCHAR(100) NOT NULL COMMENT '密码（建议加密）',
    nickname        VARCHAR(50)  NOT NULL COMMENT '昵称',
    avatar          VARCHAR(255) DEFAULT '' COMMENT '头像',
    email           VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
    stu_id          VARCHAR(20) UNIQUE COMMENT '学号',
    college         VARCHAR(50)  DEFAULT '' COMMENT '学院',
    class           VARCHAR(50)  DEFAULT '' COMMENT '专业班级',
    gender          TINYINT      DEFAULT 0 COMMENT '0未知 1男 2女',
    reg_time        DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    is_graduating   TINYINT      DEFAULT 0 COMMENT '是否应届毕业生 0否 1是',
    status          TINYINT      DEFAULT 1 COMMENT '0禁用 1正常',
    INDEX idx_stu (stu_id)
) ENGINE=InnoDB COMMENT='用户表';

-- 为 user 表添加管理员标识（默认普通用户为0，管理员为1）
ALTER TABLE user ADD COLUMN is_admin TINYINT DEFAULT 0 COMMENT '0普通用户 1管理员';

-- 可选：创建一个默认管理员账号（账号：admin 密码：admin123）
INSERT INTO user (account, password, nickname, is_admin, status) 
VALUES ('admin', 'pbkdf2:sha256:600000$xxxxxx$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', '超级管理员', 1, 1);
-- 注意：密码需用 Python 生成哈希，下面会提供生成代码
CREATE TABLE category (
    cate_id   INT PRIMARY KEY AUTO_INCREMENT COMMENT '分类ID',
    name      VARCHAR(30) NOT NULL COMMENT '分类名称',
    sort      INT DEFAULT 0 COMMENT '排序',
    enabled   TINYINT DEFAULT 1 COMMENT '是否启用'
) ENGINE=InnoDB COMMENT='商品分类表';

CREATE TABLE graduate_batch (
    batch_id      BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '批量清仓批次ID',
    user_id       BIGINT NOT NULL COMMENT '毕业生用户ID',
    batch_name    VARCHAR(100) NOT NULL COMMENT '批次名称',
    graduate_date DATE NOT NULL COMMENT '毕业日期',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX (user_id)
) ENGINE=InnoDB COMMENT='毕业生批量清仓表';

-- 第2步：创建商品表（此时 graduate_batch 已存在
CREATE TABLE goods (
    goods_id      BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '商品ID',
    title         VARCHAR(100) NOT NULL COMMENT '商品标题',
    cate_id       INT NOT NULL COMMENT '分类ID',
    user_id       BIGINT NOT NULL COMMENT '发布者ID',
    price         DECIMAL(10,2) NOT NULL COMMENT '现价',
    description   TEXT COMMENT '简介',
    degree        TINYINT DEFAULT 10 COMMENT '新旧程度1-10',
    stock         INT DEFAULT 1 COMMENT '库存',
    bargain       TINYINT DEFAULT 0 COMMENT '是否支持砍价',
    on_shelf_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '上架时间',
    sold_num      INT DEFAULT 0 COMMENT '已售数量',
    wish_num      INT DEFAULT 0 COMMENT '想要人数',
    favor_num     INT DEFAULT 0 COMMENT '收藏人数',
    view_num      INT DEFAULT 0 COMMENT '浏览量',
    is_batch      TINYINT DEFAULT 0 COMMENT '是否来自批量发布',
    batch_id      BIGINT DEFAULT NULL COMMENT '所属批量批次ID',
    status        TINYINT DEFAULT 1 COMMENT '0下架 1在售 2已售',
    INDEX idx_user (user_id),
    INDEX idx_cate (cate_id),
    INDEX idx_status (status)
) ENGINE=InnoDB COMMENT='商品表';

CREATE TABLE goods_image (
    img_id   BIGINT PRIMARY KEY AUTO_INCREMENT,
    goods_id BIGINT NOT NULL,
    url      VARCHAR(255) NOT NULL,
    sort     INT DEFAULT 0,
    INDEX (goods_id)
) ENGINE=InnoDB COMMENT='商品图片表';

CREATE TABLE `order` (
    order_id     BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_no     VARCHAR(30) NOT NULL UNIQUE,
    buyer_id     BIGINT NOT NULL,
    seller_id    BIGINT NOT NULL,
    goods_id     BIGINT NOT NULL,
    quantity     INT DEFAULT 1,
    buy_price    DECIMAL(10,2) NOT NULL COMMENT '购买时价格快照',
    total_amount DECIMAL(10,2) NOT NULL,
    pay_status   TINYINT DEFAULT 0 COMMENT '0未支付1已支付2完成3取消',
    pay_time     DATETIME DEFAULT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX (buyer_id),
    INDEX (seller_id),
    INDEX (goods_id)
) ENGINE=InnoDB COMMENT='订单表';

ALTER TABLE `order` 
ADD COLUMN confirm_time DATETIME NULL COMMENT '买家确认收货时间' AFTER pay_time,
ADD COLUMN cancel_time DATETIME NULL COMMENT '订单取消时间' AFTER confirm_time,
ADD COLUMN cancel_reason VARCHAR(100) DEFAULT NULL COMMENT '取消原因' AFTER cancel_time;

ALTER TABLE `order` ADD INDEX idx_buyer_status (buyer_id, pay_status);
ALTER TABLE `order` ADD INDEX idx_seller_status (seller_id, pay_status);

CREATE TABLE comment (
    comment_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    goods_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    parent_id  BIGINT DEFAULT 0 COMMENT '0为顶级评论',
    content    TEXT NOT NULL,
    like_count INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX (goods_id),
    INDEX (user_id)
) ENGINE=InnoDB COMMENT='评论表';

CREATE TABLE user_interaction (
    id        BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id   BIGINT NOT NULL,
    goods_id  BIGINT NOT NULL,
    type      TINYINT NOT NULL COMMENT '1收藏 2想要 3举报',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_goods_type (user_id, goods_id, type),
    INDEX (goods_id)
) ENGINE=InnoDB COMMENT='用户互动表';

CREATE TABLE message (
    msg_id      BIGINT PRIMARY KEY AUTO_INCREMENT,
    from_user_id BIGINT NOT NULL,
    to_user_id BIGINT NOT NULL,
    order_id     BIGINT DEFAULT NULL,
    content      TEXT NOT NULL,
    is_read      TINYINT DEFAULT 0,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX (to_user_id, is_read)
) ENGINE=InnoDB COMMENT='站内消息表';
ALTER TABLE message 
  ADD COLUMN from_nickname VARCHAR(50) DEFAULT '系统' COMMENT '发送者昵称缓存（系统消息用）' AFTER from_user_id,
  ADD COLUMN type ENUM('system', 'chat') NOT NULL DEFAULT 'chat' COMMENT '消息类型' AFTER order_id,
  ADD COLUMN goods_id BIGINT DEFAULT NULL COMMENT '关联商品ID' AFTER order_id,
  ADD INDEX idx_type_created (type, created_at),
  ADD INDEX idx_goods (goods_id);
  ALTER TABLE message 
ADD INDEX idx_to_created (to_user_id, created_at DESC),
ADD INDEX idx_from_to (from_user_id, to_user_id),
ADD INDEX idx_conv (from_user_id, to_user_id, created_at DESC);  -- 用于模拟会话


CREATE TABLE operation_log (
    log_id      BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id     BIGINT NOT NULL,
    action      VARCHAR(50) NOT NULL,
    target_id   BIGINT DEFAULT NULL,
    target_type VARCHAR(20) DEFAULT '',
    description  VARCHAR(255) DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='操作日志表';

-- 第3步：全部表创建完毕后，再统一添加外键（最稳妥方式）
ALTER TABLE graduate_batch   ADD FOREIGN KEY (user_id)   REFERENCES user(user_id) ON DELETE CASCADE;
ALTER TABLE goods            ADD FOREIGN KEY (user_id)   REFERENCES user(user_id) ON DELETE CASCADE;
ALTER TABLE goods            ADD FOREIGN KEY (cate_id)    REFERENCES category(cate_id);
ALTER TABLE goods            ADD FOREIGN KEY (batch_id)   REFERENCES graduate_batch(batch_id) ON DELETE SET NULL;
ALTER TABLE goods_image      ADD FOREIGN KEY (goods_id)   REFERENCES goods(goods_id) ON DELETE CASCADE;
ALTER TABLE `order`          ADD FOREIGN KEY (buyer_id)   REFERENCES user(user_id);
ALTER TABLE `order`          ADD FOREIGN KEY (seller_id)  REFERENCES user(user_id);
ALTER TABLE `order`          ADD FOREIGN KEY (goods_id)   REFERENCES goods(goods_id);
ALTER TABLE comment           ADD FOREIGN KEY (goods_id)   REFERENCES goods(goods_id) ON DELETE CASCADE;
ALTER TABLE comment           ADD FOREIGN KEY (user_id)    REFERENCES user(user_id) ON DELETE CASCADE;
ALTER TABLE user_interaction  ADD FOREIGN KEY (user_id)    REFERENCES user(user_id) ON DELETE CASCADE;
ALTER TABLE user_interaction  ADD FOREIGN KEY (goods_id)   REFERENCES goods(goods_id) ON DELETE CASCADE;
ALTER TABLE message          ADD FOREIGN KEY (from_user_id) REFERENCES user(user_id) ON DELETE CASCADE;
ALTER TABLE message          ADD FOREIGN KEY (to_user_id)   REFERENCES user(user_id) ON DELETE CASCADE;
ALTER TABLE message          ADD FOREIGN KEY (order_id)     REFERENCES `order`(order_id) ON DELETE CASCADE;
ALTER TABLE operation_log    ADD FOREIGN KEY (user_id)    REFERENCES user(user_id) ON DELETE CASCADE;


-- 1. 评论点赞表（防止重复点赞）
CREATE TABLE comment_like (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    comment_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_comment_user (comment_id, user_id),
    INDEX idx_user (user_id),
    FOREIGN KEY (comment_id) REFERENCES comment(comment_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='评论点赞记录表';

-- 2. 统一举报表（比 type=3 更专业）
CREATE TABLE report (
    report_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    reporter_id BIGINT NOT NULL COMMENT '举报人',
    target_type ENUM('goods','user') NOT NULL COMMENT 'goods=商品 user=用户',
    target_id BIGINT NOT NULL,
    reason VARCHAR(50) NOT NULL COMMENT '理由：虚假信息、价格欺诈、骚扰等',
    description VARCHAR(255) DEFAULT '' COMMENT '补充说明',
    evidence VARCHAR(255) DEFAULT '' COMMENT '截图URL（可选）',
    status TINYINT DEFAULT 0 COMMENT '0待处理 1已处理 2已忽略',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_target (target_type, target_id),
    FOREIGN KEY (reporter_id) REFERENCES user(user_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='举报表';

