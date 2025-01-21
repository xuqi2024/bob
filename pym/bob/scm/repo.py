from ..errors import BuildError
from ..stringparser import IfExpression
from ..utils import joinLines, check_output
from .scm import Scm, ScmAudit, ScmTaint, ScmStatus
from shlex import quote
from textwrap import indent
import os, os.path
import schema
import subprocess
from xml.etree import ElementTree

import re

class RepoScm(Scm):

    DEFAULTS = {
        schema.Optional('dir') : str,  # 仓库目录
    }

    __SCHEMA = {
        'scm' : 'repo',  # SCM 类型为 repo
        'url' : str,  # 仓库 URL
        schema.Optional('if') : schema.Or(str, IfExpression),  # 可能的条件表达式
        schema.Optional('revision') : schema.Or(int, str),  # 可选的版本号
        schema.Optional('manifest') : str,  # 可选的 manifest 文件
        schema.Optional('groups') : schema.Or(str, list),  # 可选的项目组
        schema.Optional('branch') : str,  # 分支
    }

    SCHEMA = schema.Schema({**__SCHEMA, **DEFAULTS})

    def __init__(self, spec, overrides=[]):
        super().__init__(spec, overrides)
        self.__url = spec["url"]
        self.__dir = spec.get("dir", ".")  # 默认目录为当前目录
        self.__revision = spec.get("revision")  # 版本号
        self.__manifest = spec.get("manifest")  # manifest 文件
        self.__groups = spec.get("groups", [])  # 项目组
        self.__branch = spec.get("branch")  # 分支


    def getProperties(self, isJenkins, pretty=False):
        ret = super().getProperties(isJenkins)
        ret.update({
            'scm' : 'repo',
            "url" : self.__url,
            "dir" : self.__dir,
        })
        if self.__revision:
            ret["revision"] = self.__revision
        if self.__manifest:
            ret["manifest"] = self.__manifest
        if self.__groups:
            ret["groups"] = self.__groups
        if self.__branch:
            ret["branch"] = self.__branch
        return ret

    # 执行 repo init 和 repo sync 命令来下载代码
    async def invoke(self, invoker):
        options = []
        if self.__branch:
            options += ["-b", str(self.__branch)]  # 指定分支或版本号
        if self.__manifest:
            options += ["-m", self.__manifest]  # 指定 manifest 文件
        if self.__groups:
            groups = ",".join(self.__groups) if isinstance(self.__groups, list) else self.__groups
            options += ["-g", groups]  # 指定项目组

        # 检查工作目录中是否已经存在 repo 配置文件
        if os.path.isdir(invoker.joinPath(self.__dir, ".repo")):
            # 如果已经存在 repo 配置文件，执行 repo sync 来同步代码
            await invoker.checkCommand(["repo", "sync", "-c", "-q","--force-sync"] , cwd=self.__dir)
        else:
            # 如果没有，则执行 repo init 来初始化仓库
            await invoker.checkCommand(["repo", "init", "-u", self.__url] + options, cwd=self.__dir)

            # 然后执行 repo sync 来下载代码
            await invoker.checkCommand(["repo", "sync", "-c", "-q","--force-sync"] , cwd=self.__dir)

    def asDigestScript(self):
        """返回一个稳定的字符串，描述当前的 repo 模块。
        模块表示为 "url[@rev] > dir" 的格式。
        """
        return (self.__url + ( ("@"+str(self.__revision)) if self.__revision else "" ) + " > "
                + self.__dir)

    def asJenkins(self, workPath, config):
        scm = ElementTree.Element("scm", attrib={
            "class" : "hudson.scm.RepoScm",
            "plugin" : "repo@1.0",
        })

        locations = ElementTree.SubElement(scm, "locations")
        location = ElementTree.SubElement(locations, "hudson.scm.RepoScm_-ModuleLocation")

        url = self.__url
        if self.__revision:
            url += ("@" + str(self.__revision))

        ElementTree.SubElement(location, "remote").text = url
        credentialsId = ElementTree.SubElement(location, "credentialsId")
        if config.credentials: credentialsId.text = config.credentials
        ElementTree.SubElement(location, "local").text = os.path.normpath(os.path.join(workPath, self.__dir))
        ElementTree.SubElement(location, "depthOption").text = "infinity"
        ElementTree.SubElement(location, "ignoreExternalsOption").text = "true"

        ElementTree.SubElement(scm, "excludedRegions")
        ElementTree.SubElement(scm, "includedRegions")
        ElementTree.SubElement(scm, "excludedUsers")
        ElementTree.SubElement(scm, "excludedRevprop")
        ElementTree.SubElement(scm, "excludedCommitMessages")
        ElementTree.SubElement(scm, "workspaceUpdater", attrib={"class":"hudson.scm.repo.UpdateUpdater"})
        ElementTree.SubElement(scm, "ignoreDirPropChanges").text = "false"
        ElementTree.SubElement(scm, "filterChangelog").text = "false"

        return scm

    def getDirectory(self):
        return self.__dir

    def isDeterministic(self):
        return str(self.__revision).isnumeric()

    def hasJenkinsPlugin(self):
        return True

    def callRepo(self, workspacePath, *args):
        cmdLine = ['repo']
        cmdLine.extend(args)
        cwd = os.path.join(workspacePath, self.__dir)
        try:
            output = subprocess.check_output(cmdLine, cwd=cwd,
                universal_newlines=True, errors='replace', stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            raise BuildError("repo error:\n Directory: '{}'\n Command: '{}'\n'{}'".format(
                cwd, " ".join(cmdLine), e.output.rstrip()))
        except OSError as e:
            raise BuildError("Error calling repo: " + str(e))
        return output.strip()

    def status(self, workspacePath):
        status = ScmStatus()
        try:
            output = self.callRepo(workspacePath, 'status')
            if output:
                status.add(ScmTaint.modified, joinLines("> modified:", indent(output, '   ')))

            output = self.callRepo(workspacePath, 'info', '--xml')
            info = ElementTree.fromstring(output)
            entry = info.find('entry')
            url = entry.find('url').text
            revision = entry.attrib['revision']

            if self.__url != url:
                status.add(ScmTaint.switched,
                    "> URL: configured: '{}', actual: '{}'".format(self.__url, url))
            if self.__revision is not None and int(revision) != int(self.__revision):
                status.add(ScmTaint.switched,
                    "> revision: configured: {}, actual: {}".format(self.__revision, revision))

        except BuildError as e:
            status.add(ScmTaint.error, e.slogan)

        return status

    def getAuditSpec(self):
        return ("repo", self.__dir, {})


class RepoAudit(ScmAudit):

    SCHEMA = schema.Schema({
        'type': 'repo',
        'dir': str,
        'url': str,
        'revision': str,
        'dirty': bool

    })

    async def _scanDir(self, workspace, dir, extra):
        self.__dir = dir
        try:
            # 获取 repo info 的输出
            info = await check_output(
                ["repo", "info"],
                cwd=workspace, universal_newlines=True, errors="replace"
            )

            # 正则表达式匹配所有项目的相关信息
            project_pattern = r"Project:\s*(.+)"
            mount_path_pattern = r"Mount path:\s*(.+)"
            current_revision_pattern = r"Current revision:\s*(\S+)"

            projects = re.findall(project_pattern, info)
            mount_paths = re.findall(mount_path_pattern, info)
            current_revisions = re.findall(current_revision_pattern, info)

            if not (projects and mount_paths and current_revisions):
                raise BuildError("Failed to parse necessary information from repo info.")

            self.__dirty = False  # 初始设为 False

            # 清理路径中的 ANSI 转义序列
            ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
            mount_paths = [ansi_escape.sub('', path) for path in mount_paths]
            current_revisions = [ansi_escape.sub('', revision) for revision in current_revisions]

            # 遍历所有项目并检查其是否有更改
            for project, mount_path, current_revision in zip(projects, mount_paths, current_revisions):
                try:
                    # 获取当前项目的 HEAD 提交
                    git_head_commit = await check_output(
                        ["git", "rev-parse", "HEAD"],
                        cwd=mount_path.strip(), universal_newlines=True, errors="replace"
                    )
                    git_head_commit = git_head_commit.strip()
                    print(git_head_commit)
                    print(current_revision)
                    # 比较当前提交和 `Current revision`
                    if git_head_commit != current_revision.strip():
                        self.__dirty = True  # 若发现任何不一致，则标记为 `dirty`
                        break  # 一旦发现有更改，直接退出检查
                except subprocess.CalledProcessError as e:
                    raise BuildError(f"Failed to get git HEAD for project {project}: {str(e)}")
                except OSError as e:
                    raise BuildError(f"Error calling git for project {project}: {str(e)}")

            # 记录最后一个项目的信息（可根据实际需要调整）
            self.__url = projects[-1].strip()
            self.__repoRoot = mount_paths[-1].strip()
            self.__revision = current_revisions[-1].strip()

        except subprocess.CalledProcessError as e:
            raise BuildError("Repo audit failed: " + str(e))
        except OSError as e:
            raise BuildError("Error calling repo: " + str(e))
        except Exception as e:
            raise BuildError(f"Unexpected error during repo scan: {str(e)}")
    print("-------------")


    def _load(self, data):
        print("_load")
        self.__dir = data["dir"]
        self.__url = data["url"]
        self.__revision = data["revision"]
        self.__dirty = data["dirty"]

    def dump(self):
        print("dump")
        return {
            "type": "repo",
            "dir": self.__dir,
            "url": self.__url,
            "revision": self.__revision,
            "dirty": self.__dirty
        }

    def getStatusLine(self):
        return self.__url + "@" + str(self.__revision) + ("-dirty" if self.__dirty else "")