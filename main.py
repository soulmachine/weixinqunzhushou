#!/usr/bin/env python3
# coding: utf-8
import json
import itchat
import datetime
from itchat.content import *
import logging
import pymongo
from bson.objectid import ObjectId
import argparse
import os
import hashlib


logging.basicConfig(level=logging.WARN,
                    handlers=[logging.FileHandler(
                        'weixinqunzhushou-' + datetime.datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S') + '.log'),
                              logging.StreamHandler()])
logger = logging.getLogger('wxqzs')


# return the user id
def upsert_user(user):
    user_from_db = db.wx_user.find_one({'Uin': user['Uin']}) if not user['Uin'] else None
    if user_from_db is None:
        user_from_db = db.wx_user.find_one({'Alias': user['Alias']}) if not user['Alias'] else None
    if user_from_db is None:
        tmp = db.wx_user.find({'NickName': user['NickName']})
        if tmp.count() == 1:
            user_from_db = list(tmp)[0]
    if user_from_db is None:
        tmp = db.wx_user.find({'HeadImgMD5': user['HeadImgMD5']})
        if tmp.count() == 1:
            user_from_db = list(tmp)[0]
    if user_from_db is None:  # new user, insert
        user['_id'] = str(ObjectId())
        user['createdAt'] = datetime.datetime.utcnow()
        db.wx_user.insert(user)
        return user['_id']
    else:  # existed user, update
        user['updatedAt'] = datetime.datetime.utcnow()
        db.wx_user.update({'_id': user_from_db['_id']}, {'$set': user})
        return user_from_db['_id']


# return the group id
def upsert_group(group):
    group_from_db = db.wx_group.find_one({'Uin': group['Uin']}) if group['Uin'] else None
    if group_from_db is None:
        group_from_db = db.wx_group.find_one({'EncryChatRoomId': group['EncryChatRoomId']})
    if group_from_db is None:
        group_from_db = db.wx_group.find_one({'UserName': group['UserName']})
    if group_from_db is None:  # new group, insert
        group['_id'] = str(ObjectId())
        group['createdAt'] = datetime.datetime.utcnow()
        db.wx_group.insert(group)
        return group['_id']
    else:  # existed group, update
        group['updatedAt'] = datetime.datetime.utcnow()
        db.wx_group.update({'_id': group_from_db['_id']}, {'$set': group})
        return group_from_db['_id']


@itchat.msg_register(TEXT, isGroupChat=True)
def groupchat_reply(msg):
    myself = itchat.get_friends()[-1]
    if myself['UserName'] == msg['FromUserName']:  # ignore messages from myself
        print('myself')
        return

    group = itchat.update_chatroom(msg['FromUserName'], detailedMember=True)
    if not group['Uin']:
        logger.warn('Uin is missing: \n' + json.dumps(group) + '\n' + json.dumps(msg))
    group_id = upsert_group(group)

    command_list = [u'菜单', u'签到', u'我的活跃度', u'活跃度排行榜', u'备份聊天记录']
    if db.msg_history.find_one({'_group_id': group_id}) is None:  # 新群
        itchat.send_msg(u'大家好，感谢群主邀请我加入本群，我是一个智能的聊天机器人，帮助群主管理本群，请大家多多关照。'
                        u'我目前能听懂的指令是:\n' + '\n'.join(command_list), msg['FromUserName'])

    user = itchat.search_friends(userName=msg['ActualUserName'])
    if user is None:
        user = [x for x in group['MemberList'] if x['UserName'] == msg['ActualUserName']][0]
    if not user['Uin'] and not user['Alias']:
        logger.warn('Both Uin and Alias are missing: \n' + json.dumps(user) + '\n' + json.dumps(msg))
    head_img_md5 = hashlib.md5(itchat.get_head_img(userName=msg['ActualUserName'],
                                                   chatroomUserName=msg['FromUserName'])).hexdigest()
    user['HeadImgMD5'] = head_img_md5
    user_id = upsert_user(user)

    msg['_id'] = msg['MsgId']
    msg['_group_id'] = group_id
    msg['_user_id'] = user_id
    db.msg_history.insert(msg)
    db.wx_group_msg_count.update({'user_id': user_id, 'group_id': group_id},
                                 {'$inc': {'msg_count': 1}, '$set': {'user_id': user_id, 'group_id': group_id}},
                                 upsert=True)

    dirty_words = ['操你妈', '草泥马', '草你妈', '傻逼']
    if any(word in msg['Content'] for word in dirty_words):
        itchat.send_msg(u'@%s\u2005辱骂性言论，超过3次将踢出本群禁言24小时' % msg['ActualNickName'], msg['FromUserName'])
        return

    if not ('isAt' in msg and msg['isAt']):  # ignore
        return

    space_index = msg['Content'].find(' ')
    if space_index == -1:
        space_index = msg['Content'].find('\u2005')
    print(space_index)
    command = msg['Content'][(space_index+1):]
    if command == u'菜单':
        itchat.send_msg((u'@%s 我目前能听懂的指令是:\n' + '\n'.join(command_list)) % msg['ActualNickName'],
                        msg['FromUserName'])
    elif command == u'签到':
        yyyymmdd = datetime.datetime.today().strftime('%Y%m%d')
        checkin_record = db.group_checkin.find_one({'_id': group_id + '-' + user_id + '-' + yyyymmdd})
        if checkin_record is None:
            db.group_checkin.insert({'_id': group_id + '-' + user_id + '-' + yyyymmdd, 'user_id': user_id,
                                     'group_id': group_id, 'createdAt': datetime.datetime.utcnow()})
            itchat.send_msg(u'@%s 签到成功' % msg['ActualNickName'], msg['FromUserName'])
        else:
            itchat.send_msg(u'@%s 你今天已经签到过了' % msg['ActualNickName'], msg['FromUserName'])
        pass
    elif command == u'活跃度排行榜':
        itchat.send_msg(u'@%s 暂未开通，敬请期待' % msg['ActualNickName'], msg['FromUserName'])
    elif command == u'我的活跃度':
        msg_count = db.msg_history.find({'_group_id': group_id, '_user_id': user_id}).count()
        checkin_count = db.group_checkin.find({'group_id': group_id, 'user_id': user_id}).count()
        itchat.send_msg(u'@%s 你的发言数: %s，签到天数: %s' % (msg['ActualNickName'], str(msg_count), str(checkin_count)),
                        msg['FromUserName'])
    elif command == u'备份聊天记录':
        messages = db.msg_history.find({'_group_id': group_id})
        text = ''
        for message in messages:
            text += json.dumps(message) + '\n'
        yyyymmdd = datetime.datetime.today().strftime('%Y%m%d')
        file_path = 'chat-history-' + yyyymmdd + '.txt'
        with open(file_path, "w") as text_file:
            text_file.write(text)
        itchat.send_msg(u'@%s 共导出%s条聊天记录' % (msg['ActualNickName'], str(messages.count())), msg['FromUserName'])
        itchat.send_file(file_path, msg['FromUserName'])
        os.remove(file_path)
    else:
        itchat.send_msg((u'@%s 未知指令，请重新输入，我目前能听懂的指令是:\n' + '\n'.join(command_list)) % msg['ActualNickName'],
                        msg['FromUserName'])


@itchat.msg_register(NOTE, isGroupChat=True)
def get_note(msg):
    msg['_id'] = msg['MsgId']
    db.msg_history.insert(msg)
    if u'邀请' in msg['Content'] or u'invited' in msg['Content']:
        pos1 = msg['Content'].rfind('"')
        pos2 = msg['Content'].rfind('"', 0, pos1)
        nick_name = msg['Content'][(pos2+1): pos1]
        itchat.send_msg(u'@%s 欢迎来到本群，我是群主的机器人助手[微笑]' % nick_name, msg['FromUserName'])


@itchat.msg_register(TEXT)
def text_reply(msg):
    itchat.send_msg(u'Hi，我是一个智能机器人，能帮助您自动化的管理微信群，把我拉入群，我就可以开始为你工作啦', msg['FromUserName'])


@itchat.msg_register(FRIENDS)
def add_friend(msg):
    itchat.add_friend(**msg['Text'])  # 该操作会自动将新好友的消息录入，不需要重载通讯录
    user_info = itchat.search_friends(userName=msg['RecommendInfo']['UserName'])
    itchat.send_msg(u'Hi，我是一个智能机器人，能帮助您自动化的管理微信群，把我拉入群，我就可以开始为你工作啦', user_info['UserName'])
    upsert_user(user_info)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start a WeChat Bot.')
    parser.add_argument('--host', help='mongodb host', default='localhost')
    parser.add_argument('--port', type=int, help='mongodb port', default=27017)
    parser.add_argument('--maintenance', type=bool, help='maintenance mode', default=False)
    args = parser.parse_args()

    maintenance_mode = args.maintenance
    # db initialize
    mongo_client = pymongo.MongoClient(args.host, args.port)
    db = mongo_client.wxqzs

    db.msg_history.create_index([('MsgId', pymongo.ASCENDING)], unique=True)
    db.wx_user.create_index([('Uin', pymongo.ASCENDING)], unique=True, sparse=True)
    db.wx_user.create_index([('Alias', pymongo.ASCENDING)], unique=True, sparse=True)
    db.wx_group.create_index([('Uin', pymongo.ASCENDING)], unique=True, sparse=True)

    itchat.auto_login(hotReload=True, enableCmdQR=2)
    itchat.run(debug=True)
