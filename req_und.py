import os

from git import Repo
from copy import deepcopy

def get_repository(repo_url, destination='./repos'):
    if not os.path.exists(destination):
        os.makedirs(destination)
    print('Start cloning repository...')
    Repo.clone_from(repo_url, destination)
    print('Repository cloned to', destination)
    return True

def main():

    repo_url = 'git@github.com:lyusupov/SoftRF.git'
    print(get_repository(repo_url, destination='./repos/SoftRF'))


if __name__ == '__main__':
    main()