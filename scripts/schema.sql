-- schema.sql
drop database if exists pblog;
create database pblog;use pblog;
grant select, insert, update, delete on pblog.* to 'x-pblog'@'localhost' identified by 'x-pblog';
-- generating SQL for blogs:
create table `blogs` (
  `id` varchar(50) not null,
  `user_id` varchar(50) not null,
  `user_name` varchar(50) not null,
  `user_image` varchar(500) not null,
  `name` varchar(50) not null,
  `summary` varchar(200) not null,
  `content` text not null,
  `created_at` real not null,
  `read_count` int default 0,
  `category` varchar(50) not null,
  `tags` varchar(50) not null,
  primary key(`id`)
)engine=innodb default charset=utf8;
-- generating SQL for comments:
create table `comments` (
  `id` varchar(50) not null,
  `blog_id` varchar(50) not null,
  `user_id` varchar(50) not null,
  `user_name` varchar(50) not null,
  `user_image` varchar(500) not null,
  `content` text not null,
  `created_at` real not null,
  primary key(`id`)
)engine=innodb default charset=utf8;
-- generating SQL for users:
create table `users` (
  `id` varchar(50) not null,
  `email` varchar(50) not null,
  `password` varchar(50) not null,
  `admin` bool not null,
  `name` varchar(50) not null,
  `image` varchar(500) not null,
  `created_at` real not null,
  primary key(`id`)
)engine=innodb default charset=utf8;
