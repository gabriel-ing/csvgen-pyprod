import iris 

def unexpire_passwords():
    iris.execute('zn "%SYS"')

    iris.Security.Users.UnExpireUserPasswords("*")


def main():

    version = "latest"

    req = iris.cls("%Net.HttpRequest")._New()
    req.Server = "pm.community.intersystems.com"
    req.SSLConfiguration = "ISC.FeatureTracker.SSL.Config"

    status = req.Get(f"/packages/zpm/{version}/installer")

    if not status:
        raise Exception("HTTP request failed")

    response = req.HttpResponse

    iris.cls("%SYSTEM.OBJ").LoadStream(response.Data, "c")

    iris.execute('zpm "enable -community" ')
    iris.execute('zn "ENSEMBLE"')
    # iris.execute('zpm "load /home/irisowner/dev -DenvSetup 1"')
    return 1


if __name__=="__main__":    
    main() 
    # unexpire_passwords()