# Created By: Virgil Dupras
# Created On: 2006/02/27
# $Id$
# Copyright 2010 Hardcoded Software (http://www.hardcoded.net)
# 
# This software is licensed under the "HS" License as described in the "LICENSE" file, 
# which should be included with this package. The terms are also available at 
# http://www.hardcoded.net/licenses/hs_license

import xml.dom.minidom

from hsutil import io
from hsutil.files import FileOrPath
from hsutil.path import Path

from . import fs

(STATE_NORMAL,
STATE_REFERENCE,
STATE_EXCLUDED) = range(3)

class AlreadyThereError(Exception):
    """The path being added is already in the directory list"""

class InvalidPathError(Exception):
    """The path being added is invalid"""

class Directories(object):
    #---Override
    def __init__(self, fileclasses=[fs.File]):
        self._dirs = []
        self.states = {}
        self.fileclasses = fileclasses
    
    def __contains__(self, path):
        for p in self._dirs:
            if path in p:
                return True
        return False
    
    def __delitem__(self,key):
        self._dirs.__delitem__(key)
    
    def __getitem__(self,key):
        return self._dirs.__getitem__(key)
    
    def __len__(self):
        return len(self._dirs)
    
    #---Private
    def _default_state_for_path(self, path):
        # Override this in subclasses to specify the state of some special folders.
        if path[-1].startswith('.'): # hidden
            return STATE_EXCLUDED
    
    def _get_files(self, from_path):
        state = self.get_state(from_path)
        if state == STATE_EXCLUDED:
            # Recursively get files from folders with lots of subfolder is expensive. However, there
            # might be a subfolder in this path that is not excluded. What we want to do is to skim
            # through self.states and see if we must continue, or we can stop right here to save time
            if not any(p[:len(from_path)] == from_path for p in self.states):
                return
        try:
            filepaths = set()
            if state != STATE_EXCLUDED:
                for file in fs.get_files(from_path, fileclasses=self.fileclasses):
                    file.is_ref = state == STATE_REFERENCE
                    filepaths.add(file.path)
                    yield file
            subpaths = [from_path + name for name in io.listdir(from_path)]
            # it's possible that a folder (bundle) gets into the file list. in that case, we don't want to recurse into it
            subfolders = [p for p in subpaths if not io.islink(p) and io.isdir(p) and p not in filepaths]
            for subfolder in subfolders:
                for file in self._get_files(subfolder):
                    yield file
        except (EnvironmentError, fs.InvalidPath):
            pass
    
    #---Public
    def add_path(self, path):
        """Adds 'path' to self, if not already there.
        
        Raises AlreadyThereError if 'path' is already in self. If path is a directory containing
        some of the directories already present in self, 'path' will be added, but all directories
        under it will be removed. Can also raise InvalidPathError if 'path' does not exist.
        """
        if path in self:
            raise AlreadyThereError()
        if not io.exists(path):
            raise InvalidPathError()
        self._dirs = [p for p in self._dirs if p not in path]
        self._dirs.append(path)
    
    @staticmethod
    def get_subfolders(path):
        """returns a sorted list of paths corresponding to subfolders in `path`"""
        try:
            names = [name for name in io.listdir(path) if io.isdir(path + name)]
            names.sort(key=lambda x:x.lower())
            return [path + name for name in names]
        except EnvironmentError:
            return []
    
    def get_files(self):
        """Returns a list of all files that are not excluded.
        
        Returned files also have their 'is_ref' attr set.
        """
        for path in self._dirs:
            for file in self._get_files(path):
                yield file
    
    def get_state(self, path):
        """Returns the state of 'path' (One of the STATE_* const.)
        """
        if path in self.states:
            return self.states[path]
        default_state = self._default_state_for_path(path)
        if default_state is not None:
            return default_state
        parent = path[:-1]
        if parent in self:
            return self.get_state(parent)
        else:
            return STATE_NORMAL
    
    def load_from_file(self, infile):
        try:
            doc = xml.dom.minidom.parse(infile)
        except:
            return
        root_path_nodes = doc.getElementsByTagName('root_directory')
        for rdn in root_path_nodes:
            if not rdn.getAttributeNode('path'):
                continue
            path = rdn.getAttributeNode('path').nodeValue
            try:
                self.add_path(Path(path))
            except (AlreadyThereError, InvalidPathError):
                pass
        state_nodes = doc.getElementsByTagName('state')
        for sn in state_nodes:
            if not (sn.getAttributeNode('path') and sn.getAttributeNode('value')):
                continue
            path = sn.getAttributeNode('path').nodeValue
            state = sn.getAttributeNode('value').nodeValue
            self.set_state(Path(path), int(state))
    
    def save_to_file(self,outfile):
        with FileOrPath(outfile, 'wb') as fp:
            doc = xml.dom.minidom.Document()
            root = doc.appendChild(doc.createElement('directories'))
            for root_path in self:
                root_path_node = root.appendChild(doc.createElement('root_directory'))
                root_path_node.setAttribute('path', unicode(root_path).encode('utf-8'))
            for path, state in self.states.iteritems():
                state_node = root.appendChild(doc.createElement('state'))
                state_node.setAttribute('path', unicode(path).encode('utf-8'))
                state_node.setAttribute('value', str(state))
            doc.writexml(fp, '\t', '\t', '\n', encoding='utf-8')
    
    def set_state(self, path, state):
        if self.get_state(path) == state:
            return
        # we don't want to needlessly fill self.states. if get_state returns the same thing
        # without an explicit entry, remove that entry
        if path in self.states:
            del self.states[path]
            if self.get_state(path) == state: # no need for an entry
                return
        self.states[path] = state
    
